from __future__ import annotations

import json
from base64 import b64encode, urlsafe_b64encode
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

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


def _browser_settings(*, client_secret: str = "") -> Settings:
    return Settings(
        oidc_issuer=ISSUER,
        oidc_audience=AUDIENCE,
        oidc_jwks_url="https://idp.example.com/.well-known/jwks.json",
        oidc_runner_groups=["incidentlens-runners"],
        oidc_admin_groups=["incidentlens-admins"],
        oidc_authorization_url="https://idp.example.com/oauth2/authorize",
        oidc_token_url="https://idp.example.com/oauth2/token",
        oidc_client_id="incidentlens-web",
        oidc_client_secret=client_secret,
        oidc_redirect_uri="https://incidentlens.example.com/api/v1/auth/callback",
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
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(UTC)
    claims: dict[str, object] = {
        "iss": issuer,
        "sub": subject,
        "aud": audience,
        "iat": int((issued_at - timedelta(seconds=1)).timestamp()),
        "exp": int((issued_at + expires_delta).timestamp()),
        "groups": groups,
    }
    claims.update(extra_claims or {})
    return jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": kid, "typ": token_type},
    )


def _id_token(
    *,
    nonce: str,
    access_token: str,
    subject: str = "user-123",
    audience: object = "incidentlens-web",
    at_hash: str | None = None,
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(UTC)
    digest = sha256(access_token.encode()).digest()
    calculated_at_hash = (
        urlsafe_b64encode(digest[: len(digest) // 2])
        .rstrip(b"=")
        .decode("ascii")
    )
    return jwt.encode(
        {
            "iss": ISSUER,
            "sub": subject,
            "aud": audience,
            "iat": int((issued_at - timedelta(seconds=1)).timestamp()),
            "exp": int((issued_at + timedelta(minutes=5)).timestamp()),
            "nonce": nonce,
            "at_hash": at_hash or calculated_at_hash,
        },
        PRIVATE_KEY,
        algorithm="RS256",
        headers={"kid": "key-1", "typ": "JWT"},
    )


def _verifier(
    endpoint: Callable[[httpx.Request], httpx.Response],
    *,
    clock: Callable[[], float] | None = None,
    deadline_clock: Callable[[], float] | None = None,
    settings: Settings | None = None,
) -> OidcTokenVerifier:
    client = httpx.Client(transport=httpx.MockTransport(endpoint))
    return OidcTokenVerifier(
        settings or _settings(),
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


def test_oidc_access_token_exposes_subject_and_expiry_for_a_server_session() -> None:
    endpoint = JwksEndpoint([_jwk(PRIVATE_KEY, "key-1")])
    verifier = _verifier(endpoint)
    now = datetime.now(UTC).replace(microsecond=0)

    verified = verifier.verify_for_session(
        _token(
            subject="session-user",
            groups=["incidentlens-admins"],
            expires_delta=timedelta(minutes=7),
            now=now,
        )
    )

    assert verified is not None
    assert verified.subject == "session-user"
    assert verified.expires_at == now + timedelta(minutes=7)
    assert verified.principal.role == "admin"


def test_oidc_id_token_is_bound_to_nonce_client_subject_and_access_token() -> None:
    endpoint = JwksEndpoint([_jwk(PRIVATE_KEY, "key-1")])
    verifier = _verifier(endpoint, settings=_browser_settings())
    now = datetime.now(UTC).replace(microsecond=0)
    access_token = _token(now=now)

    verified = verifier.verify_id_token(
        _id_token(
            nonce="one-time-nonce",
            access_token=access_token,
            now=now,
        ),
        nonce="one-time-nonce",
        access_token=access_token,
        expected_subject="user-123",
    )

    assert verified is not None
    assert verified.subject == "user-123"
    assert verified.expires_at == now + timedelta(minutes=5)


def test_oidc_id_token_rejects_replay_and_token_substitution() -> None:
    endpoint = JwksEndpoint([_jwk(PRIVATE_KEY, "key-1")])
    verifier = _verifier(endpoint, settings=_browser_settings())
    access_token = _token()
    valid = _id_token(nonce="expected-nonce", access_token=access_token)

    assert (
        verifier.verify_id_token(
            valid,
            nonce="replayed-nonce",
            access_token=access_token,
            expected_subject="user-123",
        )
        is None
    )
    assert (
        verifier.verify_id_token(
            _id_token(
                nonce="expected-nonce",
                access_token=access_token,
                audience="attacker-client",
            ),
            nonce="expected-nonce",
            access_token=access_token,
            expected_subject="user-123",
        )
        is None
    )
    assert (
        verifier.verify_id_token(
            _id_token(
                nonce="expected-nonce",
                access_token=access_token,
                subject="different-user",
            ),
            nonce="expected-nonce",
            access_token=access_token,
            expected_subject="user-123",
        )
        is None
    )
    assert (
        verifier.verify_id_token(
            _id_token(
                nonce="expected-nonce",
                access_token=access_token,
                at_hash="attacker-controlled-hash",
            ),
            nonce="expected-nonce",
            access_token=access_token,
            expected_subject="user-123",
        )
        is None
    )


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


def test_browser_oidc_authorization_uses_state_nonce_and_pkce_s256() -> None:
    from incidentlens.oidc_browser import OidcBrowserClient

    settings = _browser_settings()
    endpoint = JwksEndpoint([_jwk(PRIVATE_KEY, "key-1")])
    client = OidcBrowserClient(
        settings,
        OidcTokenVerifier(
            settings,
            http_client=httpx.Client(transport=httpx.MockTransport(endpoint)),
        ),
    )

    started = client.begin_authorization()
    query = parse_qs(urlsplit(started.authorization_url).query)
    expected_challenge = (
        urlsafe_b64encode(sha256(started.code_verifier.encode()).digest())
        .rstrip(b"=")
        .decode("ascii")
    )

    assert query == {
        "response_type": ["code"],
        "client_id": ["incidentlens-web"],
        "redirect_uri": [
            "https://incidentlens.example.com/api/v1/auth/callback"
        ],
        "scope": ["openid"],
        "state": [started.state],
        "nonce": [started.nonce],
        "code_challenge": [expected_challenge],
        "code_challenge_method": ["S256"],
    }
    assert 43 <= len(started.state) <= 128
    assert 43 <= len(started.browser_token) <= 128
    assert 43 <= len(started.code_verifier) <= 128
    assert 43 <= len(started.nonce) <= 128
    assert started.code_verifier not in started.authorization_url
    client.close()


def test_browser_oidc_exchanges_code_and_validates_both_tokens() -> None:
    from incidentlens.oidc_browser import OidcBrowserClient

    now = datetime.now(UTC).replace(microsecond=0)
    access_token = _token(
        groups=["incidentlens-admins"],
        expires_delta=timedelta(minutes=7),
        now=now,
    )
    id_token = _id_token(
        nonce="callback-nonce",
        access_token=access_token,
        now=now,
    )
    settings = _browser_settings(client_secret="client secret/+")

    def provider(request: httpx.Request) -> httpx.Response:
        if request.url == "https://idp.example.com/.well-known/jwks.json":
            return httpx.Response(
                200,
                stream=httpx.ByteStream(
                    json.dumps(
                        {"keys": [_jwk(PRIVATE_KEY, "key-1")]}
                    ).encode()
                ),
            )
        assert request.url == "https://idp.example.com/oauth2/token"
        assert request.method == "POST"
        encoded_client = quote("incidentlens-web", safe="")
        encoded_secret = quote("client secret/+", safe="")
        expected_basic = b64encode(
            f"{encoded_client}:{encoded_secret}".encode()
        ).decode()
        assert request.headers["Authorization"] == f"Basic {expected_basic}"
        assert parse_qs(request.content.decode()) == {
            "grant_type": ["authorization_code"],
            "code": ["one-time-code"],
            "redirect_uri": [
                "https://incidentlens.example.com/api/v1/auth/callback"
            ],
            "code_verifier": ["callback-verifier"],
        }
        document = json.dumps(
            {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 420,
                "id_token": id_token,
                "refresh_token": "must-not-be-persisted",
                "ignored": "[" * 100,
            }
        ).encode()
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            stream=httpx.ByteStream(document),
        )

    http_client = httpx.Client(transport=httpx.MockTransport(provider))
    verifier = OidcTokenVerifier(settings, http_client=http_client)
    client = OidcBrowserClient(
        settings,
        verifier,
        http_client=http_client,
    )

    identity = client.exchange_code(
        code="one-time-code",
        code_verifier="callback-verifier",
        nonce="callback-nonce",
    )

    assert identity.principal.role == "admin"
    assert identity.expires_at == now + timedelta(minutes=5)
    client.close()


def test_browser_oidc_stops_reading_an_oversized_token_response() -> None:
    from incidentlens.oidc_browser import OidcBrowserClient

    settings = _browser_settings()
    stream = CountingStream([b"x" * 65_536 for _ in range(32)])

    def oversized(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            stream=stream,
        )

    http_client = httpx.Client(transport=httpx.MockTransport(oversized))
    client = OidcBrowserClient(
        settings,
        OidcTokenVerifier(settings, http_client=http_client),
        http_client=http_client,
    )

    with pytest.raises(AuthenticationUnavailable):
        client.exchange_code(
            code="one-time-code",
            code_verifier="callback-verifier",
            nonce="callback-nonce",
        )
    assert stream.chunks_read < len(stream.chunks)


def test_browser_oidc_stops_a_slow_token_response_at_the_total_deadline() -> None:
    from incidentlens.oidc_browser import OidcBrowserClient

    settings = _browser_settings()
    deadline_clock = Clock()
    stream = CountingStream(
        [b'{"access_token":', b'"never-finishes"', b"}"],
        clock=deadline_clock,
        seconds_per_chunk=3.0,
    )

    def slow(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=stream)

    http_client = httpx.Client(transport=httpx.MockTransport(slow))
    client = OidcBrowserClient(
        settings,
        OidcTokenVerifier(settings, http_client=http_client),
        http_client=http_client,
        deadline_clock=deadline_clock,
    )

    with pytest.raises(AuthenticationUnavailable):
        client.exchange_code(
            code="one-time-code",
            code_verifier="callback-verifier",
            nonce="callback-nonce",
        )
    assert stream.chunks_read == 2


def test_browser_oidc_treats_deeply_nested_token_json_as_unavailable() -> None:
    from incidentlens.oidc_browser import OidcBrowserClient

    settings = _browser_settings()
    document = b'{"value":' + b"[" * 100 + b"]" * 100 + b"}"

    def deeply_nested(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=httpx.ByteStream(document))

    http_client = httpx.Client(transport=httpx.MockTransport(deeply_nested))
    client = OidcBrowserClient(
        settings,
        OidcTokenVerifier(settings, http_client=http_client),
        http_client=http_client,
    )

    with pytest.raises(AuthenticationUnavailable):
        client.exchange_code(
            code="one-time-code",
            code_verifier="callback-verifier",
            nonce="callback-nonce",
        )


def test_browser_oidc_accepts_matching_unicode_subject_and_nonce() -> None:
    settings = _browser_settings()
    endpoint = JwksEndpoint([_jwk(PRIVATE_KEY, "key-1")])
    verifier = _verifier(endpoint, settings=settings)
    access_token = _token(subject="用户")
    id_token = _id_token(
        subject="用户",
        nonce="登录-随机值",
        access_token=access_token,
    )
    verified_access = verifier.verify_for_session(access_token)

    assert verified_access is not None
    assert (
        verifier.verify_id_token(
            id_token,
            nonce="登录-随机值",
            access_token=access_token,
            expected_subject=verified_access.subject,
        )
        is not None
    )
