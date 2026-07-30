from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from incidentlens.auth import AuthenticationUnavailable, Principal
from incidentlens.config import Settings
from incidentlens.oidc import OidcTokenVerifier
from jwt.algorithms import RSAAlgorithm

ISSUER = "https://idp.example.com"
AUDIENCE = "incidentlens-api"
PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ROTATED_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
WEAK_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=1024)


def _jwk(private_key: rsa.RSAPrivateKey, kid: str) -> dict[str, Any]:
    value = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    value.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return value


class JwksEndpoint:
    def __init__(self, keys: list[dict[str, Any]]) -> None:
        self.keys = keys
        self.calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url == "https://idp.example.com/.well-known/jwks.json"
        self.calls += 1
        document = json.dumps({"keys": self.keys}).encode()
        return httpx.Response(200, stream=httpx.ByteStream(document))


class Clock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class CountingStream(httpx.SyncByteStream):
    def __init__(
        self,
        chunks: list[bytes],
        *,
        clock: Clock | None = None,
        seconds_per_chunk: float = 0.0,
    ) -> None:
        self.chunks = chunks
        self.clock = clock
        self.seconds_per_chunk = seconds_per_chunk
        self.chunks_read = 0

    def __iter__(self) -> Any:
        for chunk in self.chunks:
            self.chunks_read += 1
            if self.clock is not None:
                self.clock.advance(self.seconds_per_chunk)
            yield chunk


def _settings() -> Settings:
    return Settings(
        oidc_issuer=ISSUER,
        oidc_audience=AUDIENCE,
        oidc_jwks_url="https://idp.example.com/.well-known/jwks.json",
        oidc_runner_groups=["incidentlens-runners"],
        oidc_admin_groups=["incidentlens-admins"],
        _env_file=None,
    )


def _token(
    *,
    private_key: rsa.RSAPrivateKey = PRIVATE_KEY,
    kid: str = "key-1",
    subject: str = "user-123",
    groups: object = ("incidentlens-runners",),
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    expires_delta: timedelta = timedelta(minutes=5),
    extra_claims: dict[str, object] | None = None,
    token_type: str = "at+jwt",
) -> str:
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "iss": issuer,
        "sub": subject,
        "aud": audience,
        "iat": int((now - timedelta(seconds=1)).timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "groups": groups,
    }
    claims.update(extra_claims or {})
    return jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": kid, "typ": token_type},
    )


def _verifier(
    endpoint: Callable[[httpx.Request], httpx.Response],
    *,
    clock: Callable[[], float] | None = None,
    deadline_clock: Callable[[], float] | None = None,
) -> OidcTokenVerifier:
    client = httpx.Client(transport=httpx.MockTransport(endpoint))
    return OidcTokenVerifier(
        _settings(),
        http_client=client,
        clock=clock,
        deadline_clock=deadline_clock,
    )


def test_oidc_verifier_maps_groups_and_uses_stable_issuer_subject_identity() -> None:
    endpoint = JwksEndpoint([_jwk(PRIVATE_KEY, "key-1")])
    verifier = _verifier(endpoint)

    first = verifier.verify(
        _token(
            groups=["incidentlens-admins"],
            extra_claims={"preferred_username": "alice"},
        )
    )
    refreshed = verifier.verify(
        _token(
            groups=["incidentlens-admins"],
            extra_claims={"preferred_username": "renamed-alice"},
        )
    )

    expected = Principal(
        role="admin",
        actor="oidc-V5ynxbkKlx4fB592YfPLFGpXClfSlAutxFHkDEwMHsg",
        token_hash="579ca7c5b90a971e1f079f7661f3cb146a570a57d2940badc451e40c4c0c1ec8",
    )
    assert first == expected
    assert refreshed == expected
    assert endpoint.calls == 1


def test_oidc_actor_is_collision_resistant_for_every_subject_format() -> None:
    endpoint = JwksEndpoint([_jwk(PRIVATE_KEY, "key-1")])
    verifier = _verifier(endpoint)
    unsafe_subject = "é"
    formerly_colliding_subject = sha256(unsafe_subject.encode()).hexdigest()[:32]

    unsafe = verifier.verify(_token(subject=unsafe_subject))
    safe = verifier.verify(_token(subject=formerly_colliding_subject))

    assert unsafe is not None
    assert safe is not None
    assert unsafe.actor != safe.actor


def test_oidc_verifier_rejects_unmapped_or_malformed_group_claims() -> None:
    endpoint = JwksEndpoint([_jwk(PRIVATE_KEY, "key-1")])
    verifier = _verifier(endpoint)

    assert verifier.verify(_token()) is not None
    assert verifier.verify(_token(groups=["unmapped-group"])) is None
    assert verifier.verify(_token(groups="incidentlens-runners")) is None


def test_oidc_verifier_rejects_invalid_trust_and_time_claims() -> None:
    endpoint = JwksEndpoint([_jwk(PRIVATE_KEY, "key-1")])
    verifier = _verifier(endpoint)

    assert verifier.verify(_token()) is not None
    assert verifier.verify(_token(audience="different-api")) is None
    assert verifier.verify(_token(issuer="https://attacker.example.com")) is None
    assert verifier.verify(_token(expires_delta=timedelta(minutes=-5))) is None
    assert verifier.verify(_token(token_type="JWT")) is None


def test_unknown_signing_keys_refresh_only_after_the_cooldown() -> None:
    clock = Clock()
    endpoint = JwksEndpoint([_jwk(PRIVATE_KEY, "key-1")])
    verifier = _verifier(endpoint, clock=clock)
    rotated = _token(
        private_key=ROTATED_PRIVATE_KEY,
        kid="key-2",
    )

    assert verifier.verify(_token()) is not None
    assert verifier.verify(rotated) is None
    assert verifier.verify(rotated) is None
    assert endpoint.calls == 1

    clock.advance(31)
    endpoint.keys = [
        _jwk(PRIVATE_KEY, "key-1"),
        _jwk(ROTATED_PRIVATE_KEY, "key-2"),
    ]

    assert verifier.verify(rotated) is not None
    assert endpoint.calls == 2


def test_oidc_verifier_accepts_safe_rs256_key_from_a_mixed_jwks() -> None:
    encryption_key = _jwk(ROTATED_PRIVATE_KEY, "encryption-key")
    encryption_key.update({"alg": "RSA-OAEP-256", "use": "enc"})
    endpoint = JwksEndpoint(
        [
            {"kty": "EC", "kid": "ec-signing-key", "alg": "ES256", "use": "sig"},
            encryption_key,
            _jwk(PRIVATE_KEY, "key-1"),
        ]
    )
    verifier = _verifier(endpoint)

    assert verifier.verify(_token()) is not None


def test_oidc_verifier_stops_reading_an_oversized_jwks_stream() -> None:
    stream = CountingStream([b"x" * 65_536 for _ in range(32)])

    def oversized(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=stream)

    verifier = _verifier(oversized)

    with pytest.raises(AuthenticationUnavailable):
        verifier.verify(_token())
    assert stream.chunks_read < len(stream.chunks)


def test_oidc_verifier_stops_a_slow_jwks_stream_at_the_total_deadline() -> None:
    deadline_clock = Clock()
    stream = CountingStream(
        [b'{"keys":', b"[]}", b"ignored"],
        clock=deadline_clock,
        seconds_per_chunk=2.0,
    )

    def slow(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=stream)

    verifier = _verifier(slow, deadline_clock=deadline_clock)

    with pytest.raises(AuthenticationUnavailable):
        verifier.verify(_token())
    assert stream.chunks_read == 2


def test_oidc_verifier_treats_deeply_nested_jwks_json_as_unavailable() -> None:
    document = b'{"keys":' + b"[" * 5_000 + b"]" * 5_000 + b"}"

    def deeply_nested(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=httpx.ByteStream(document))

    verifier = _verifier(deeply_nested)

    with pytest.raises(AuthenticationUnavailable):
        verifier.verify(_token())


def test_oidc_verifier_fails_closed_when_the_jwks_endpoint_is_unavailable() -> None:
    attempts = 0

    def unavailable(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("unavailable", request=request)

    verifier = _verifier(unavailable)

    with pytest.raises(AuthenticationUnavailable):
        verifier.verify(_token())
    with pytest.raises(AuthenticationUnavailable):
        verifier.verify(_token())
    assert attempts == 1


def test_oidc_verifier_fails_closed_for_a_malformed_signing_key() -> None:
    endpoint = JwksEndpoint(
        [
            {
                "kid": "key-1",
                "kty": "RSA",
                "alg": "RS256",
                "use": "sig",
                "e": "AQAB",
            }
        ]
    )
    verifier = _verifier(endpoint)

    with pytest.raises(AuthenticationUnavailable):
        verifier.verify(_token())


def test_oidc_verifier_rejects_a_weak_rsa_signing_key() -> None:
    endpoint = JwksEndpoint([_jwk(WEAK_PRIVATE_KEY, "weak-key")])
    verifier = _verifier(endpoint)
    with pytest.warns(jwt.InsecureKeyLengthWarning):
        token = _token(
            private_key=WEAK_PRIVATE_KEY,
            kid="weak-key",
        )

    with pytest.raises(AuthenticationUnavailable):
        verifier.verify(token)
