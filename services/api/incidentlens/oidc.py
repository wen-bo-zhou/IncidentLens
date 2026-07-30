from __future__ import annotations

import json
from base64 import urlsafe_b64encode
from collections.abc import Callable
from hashlib import sha256
from threading import Lock
from time import monotonic
from typing import Any, cast

import httpx
import jwt
from jwt import InvalidTokenError, PyJWK, PyJWTError

from incidentlens.auth import AuthenticationUnavailable, Principal, Role
from incidentlens.config import Settings

_ALGORITHM = "RS256"
_JWKS_CACHE_SECONDS = 300.0
_JWKS_REFRESH_COOLDOWN_SECONDS = 30.0
_MAX_JWKS_BYTES = 1_000_000
_MAX_JWKS_KEYS = 100
_MAX_TOKEN_BYTES = 16_384
_JWKS_TOTAL_DEADLINE_SECONDS = 3.0


class OidcTokenVerifier:
    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.Client | None = None,
        clock: Callable[[], float] | None = None,
        deadline_clock: Callable[[], float] | None = None,
    ) -> None:
        if not settings.oidc_enabled:
            raise ValueError("OIDC verifier requires a complete OIDC configuration")
        self.settings = settings
        self._http_client = http_client or httpx.Client(
            timeout=httpx.Timeout(connect=3.0, read=0.25, write=3.0, pool=3.0),
            follow_redirects=False,
        )
        self._owns_http_client = http_client is None
        self._clock = clock or monotonic
        self._deadline_clock = deadline_clock or monotonic
        self._lock = Lock()
        self._keys: dict[str, PyJWK] = {}
        self._expires_at = 0.0
        self._last_refresh_at = float("-inf")

    def close(self) -> None:
        if self._owns_http_client:
            self._http_client.close()

    def verify(self, token: str) -> Principal | None:
        if len(token.encode("utf-8")) > _MAX_TOKEN_BYTES or token.count(".") != 2:
            return None
        try:
            header = jwt.get_unverified_header(token)
        except InvalidTokenError:
            return None
        if (
            header.get("alg") != _ALGORITHM
            or str(header.get("typ", "")).lower() != "at+jwt"
            or any(name in header for name in ("jku", "jwk", "x5u", "x5c"))
        ):
            return None
        kid = header.get("kid")
        if not isinstance(kid, str) or not 1 <= len(kid) <= 128:
            return None
        key = self._signing_key(kid)
        if key is None:
            return None
        try:
            claims = jwt.decode(
                token,
                key=key,
                algorithms=[_ALGORITHM],
                audience=self.settings.oidc_audience,
                issuer=self.settings.oidc_issuer,
                leeway=30,
                options={
                    "require": ["iss", "sub", "aud", "iat", "exp"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_nbf": True,
                    "verify_iss": True,
                    "verify_aud": True,
                    "verify_sub": True,
                },
            )
        except InvalidTokenError:
            return None
        return self._principal_from_claims(claims)

    def _signing_key(self, kid: str) -> PyJWK | None:
        now = self._clock()
        with self._lock:
            if now >= self._expires_at:
                if now - self._last_refresh_at < _JWKS_REFRESH_COOLDOWN_SECONDS:
                    raise AuthenticationUnavailable
                if not self._refresh_keys(now):
                    raise AuthenticationUnavailable
            key = self._keys.get(kid)
            if key is not None:
                return key
            if now - self._last_refresh_at < _JWKS_REFRESH_COOLDOWN_SECONDS:
                return None
            if not self._refresh_keys(now):
                raise AuthenticationUnavailable
            return self._keys.get(kid)

    def _refresh_keys(self, now: float) -> bool:
        self._last_refresh_at = now
        try:
            document = self._fetch_jwks_document()
            if document is None:
                return False
            payload = json.loads(document)
            if not isinstance(payload, dict):
                return False
            raw_keys = payload.get("keys")
            if (
                not isinstance(raw_keys, list)
                or not raw_keys
                or len(raw_keys) > _MAX_JWKS_KEYS
            ):
                return False
            keys: dict[str, PyJWK] = {}
            candidate_kids: set[str] = set()
            for value in raw_keys:
                if not isinstance(value, dict):
                    continue
                if (
                    value.get("kty") != "RSA"
                    or value.get("alg") not in (None, _ALGORITHM)
                    or value.get("use") not in (None, "sig")
                ):
                    continue
                key_ops = value.get("key_ops")
                if key_ops is not None and (
                    not isinstance(key_ops, list) or "verify" not in key_ops
                ):
                    continue
                kid = value.get("kid")
                if not isinstance(kid, str) or not 1 <= len(kid) <= 128:
                    continue
                if kid in candidate_kids:
                    return False
                candidate_kids.add(kid)
                try:
                    key = PyJWK.from_dict(
                        cast(Any, value),
                        algorithm=_ALGORITHM,
                    )
                except (PyJWTError, TypeError, ValueError):
                    continue
                if getattr(key.key, "key_size", 0) < 2048:
                    continue
                keys[kid] = key
        except (
            httpx.HTTPError,
            PyJWTError,
            RecursionError,
            TypeError,
            ValueError,
        ):
            return False
        if not keys:
            return False
        self._keys = keys
        self._expires_at = now + _JWKS_CACHE_SECONDS
        return True

    def _fetch_jwks_document(self) -> bytes | None:
        started_at = self._deadline_clock()
        content = bytearray()
        with self._http_client.stream(
            "GET",
            self.settings.oidc_jwks_url,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
            },
        ) as response:
            response.raise_for_status()
            if self._deadline_exceeded(started_at):
                return None
            content_encoding = response.headers.get("Content-Encoding", "identity")
            if content_encoding.lower().strip() not in {"", "identity"}:
                return None
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                try:
                    if int(content_length) > _MAX_JWKS_BYTES:
                        return None
                except ValueError:
                    return None
            for chunk in response.iter_raw():
                if self._deadline_exceeded(started_at):
                    return None
                if len(content) + len(chunk) > _MAX_JWKS_BYTES:
                    return None
                content.extend(chunk)
            if self._deadline_exceeded(started_at):
                return None
        return bytes(content)

    def _deadline_exceeded(self, started_at: float) -> bool:
        return (
            self._deadline_clock() - started_at
            > _JWKS_TOTAL_DEADLINE_SECONDS
        )

    def _principal_from_claims(self, claims: dict[str, Any]) -> Principal | None:
        subject = claims.get("sub")
        groups_value = claims.get(self.settings.oidc_groups_claim)
        if (
            not isinstance(subject, str)
            or not 1 <= len(subject) <= 255
            or not isinstance(groups_value, list)
            or len(groups_value) > 256
            or any(
                not isinstance(group, str) or not 1 <= len(group) <= 128
                for group in groups_value
            )
        ):
            return None
        groups = set(groups_value)
        role: Role | None = None
        if groups.intersection(self.settings.oidc_admin_groups):
            role = "admin"
        elif groups.intersection(self.settings.oidc_runner_groups):
            role = "runner"
        if role is None:
            return None
        identity_digest = sha256(
            f"{self.settings.oidc_issuer}\0{subject}".encode()
        ).digest()
        identity_hash = identity_digest.hex()
        actor = (
            "oidc-"
            + urlsafe_b64encode(identity_digest).rstrip(b"=").decode("ascii")
        )
        return Principal(
            role=role,
            actor=actor,
            token_hash=identity_hash,
        )
