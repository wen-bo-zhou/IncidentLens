from __future__ import annotations

import json
from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from incidentlens.app import create_app
from incidentlens.config import Settings
from incidentlens.observability import redact_access_log_path
from incidentlens.oidc import OidcTokenVerifier
from incidentlens.oidc_browser import OidcBrowserClient
from jwt.algorithms import RSAAlgorithm

_ISSUER = "https://idp.example.com"
_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk() -> dict[str, Any]:
    value = RSAAlgorithm.to_jwk(_PRIVATE_KEY.public_key(), as_dict=True)
    value.update({"kid": "browser-key", "use": "sig", "alg": "RS256"})
    return value


class BrowserIdentityProvider:
    def __init__(self) -> None:
        self.nonce = ""
        self.token_calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url == f"{_ISSUER}/jwks":
            return self._json_stream({"keys": [_jwk()]})
        if request.url == f"{_ISSUER}/token":
            self.token_calls += 1
            now = datetime.now(UTC)
            access_token = self._access_token(now)
            return self._json_stream(
                {
                    "access_token": access_token,
                    "token_type": "Bearer",
                    "expires_in": 600,
                    "id_token": self._id_token(now, access_token),
                }
            )
        raise AssertionError(f"Unexpected IdP request: {request.url}")

    def _access_token(self, now: datetime) -> str:
        return jwt.encode(
            {
                "iss": _ISSUER,
                "sub": "browser-user",
                "aud": "incidentlens-api",
                "iat": int((now - timedelta(seconds=1)).timestamp()),
                "exp": int((now + timedelta(minutes=10)).timestamp()),
                "groups": ["incidentlens-admins"],
            },
            _PRIVATE_KEY,
            algorithm="RS256",
            headers={"kid": "browser-key", "typ": "at+jwt"},
        )

    def _id_token(self, now: datetime, access_token: str) -> str:
        digest = sha256(access_token.encode()).digest()
        at_hash = (
            urlsafe_b64encode(digest[: len(digest) // 2])
            .rstrip(b"=")
            .decode("ascii")
        )
        return jwt.encode(
            {
                "iss": _ISSUER,
                "sub": "browser-user",
                "aud": "incidentlens-web",
                "iat": int((now - timedelta(seconds=1)).timestamp()),
                "exp": int((now + timedelta(minutes=10)).timestamp()),
                "nonce": self.nonce,
                "at_hash": at_hash,
            },
            _PRIVATE_KEY,
            algorithm="RS256",
            headers={"kid": "browser-key", "typ": "JWT"},
        )

    @staticmethod
    def _json_stream(payload: dict[str, Any]) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            stream=httpx.ByteStream(json.dumps(payload).encode()),
        )


def _browser_client(
    **settings_overrides: object,
) -> tuple[TestClient, BrowserIdentityProvider]:
    settings_values: dict[str, object] = {
        "oidc_issuer": _ISSUER,
        "oidc_audience": "incidentlens-api",
        "oidc_jwks_url": f"{_ISSUER}/jwks",
        "oidc_runner_groups": ["incidentlens-runners"],
        "oidc_admin_groups": ["incidentlens-admins"],
        "oidc_authorization_url": f"{_ISSUER}/authorize",
        "oidc_token_url": f"{_ISSUER}/token",
        "oidc_client_id": "incidentlens-web",
        "oidc_client_secret": "test-browser-client-secret",
        "oidc_redirect_uri": "http://testserver/api/v1/auth/callback",
    }
    settings_values.update(settings_overrides)
    settings = Settings(_env_file=None, **settings_values)
    provider = BrowserIdentityProvider()
    http_client = httpx.Client(transport=httpx.MockTransport(provider))
    verifier = OidcTokenVerifier(settings, http_client=http_client)
    browser_client = OidcBrowserClient(
        settings,
        verifier,
        http_client=http_client,
    )
    app = create_app(
        testing=True,
        settings=settings,
        oidc_verifier=verifier,
        oidc_browser_client=browser_client,
    )
    base_url = (
        "https://testserver"
        if settings.app_env == "production"
        else "http://testserver"
    )
    return TestClient(app, base_url=base_url), provider


def _sign_in(
    client: TestClient,
    provider: BrowserIdentityProvider,
    *,
    return_to: str = "/operations",
) -> httpx.Response:
    login = client.get(
        "/api/v1/auth/login",
        params={"return_to": return_to},
        follow_redirects=False,
    )
    assert login.status_code == 302
    query = parse_qs(urlsplit(login.headers["Location"]).query)
    provider.nonce = query["nonce"][0]
    callback = client.get(
        "/api/v1/auth/callback",
        params={"code": "one-time-code", "state": query["state"][0]},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    return callback


def test_browser_login_callback_creates_only_an_http_only_server_session() -> None:
    client, provider = _browser_client()

    login = client.get(
        "/api/v1/auth/login",
        params={"return_to": "/operations"},
        follow_redirects=False,
    )
    query = parse_qs(urlsplit(login.headers["Location"]).query)
    provider.nonce = query["nonce"][0]
    callback = client.get(
        "/api/v1/auth/callback",
        params={"code": "one-time-code", "state": query["state"][0]},
        follow_redirects=False,
    )
    session = client.get("/api/v1/auth/session")

    assert login.status_code == 302
    assert "incidentlens_oidc_transaction=" in login.headers["Set-Cookie"]
    assert "HttpOnly" in login.headers["Set-Cookie"]
    assert "SameSite=lax" in login.headers["Set-Cookie"]
    assert callback.status_code == 302
    assert callback.headers["Location"] == "/operations"
    assert "incidentlens_session=" in callback.headers["Set-Cookie"]
    assert "HttpOnly" in callback.headers["Set-Cookie"]
    assert "SameSite=strict" in callback.headers["Set-Cookie"]
    assert callback.headers["Cache-Control"] == "no-store"
    assert callback.headers["Referrer-Policy"] == "no-referrer"
    assert session.status_code == 200
    assert session.json()["authenticated"] is True
    assert session.json()["sso_enabled"] is True
    assert session.json()["role"] == "admin"
    assert session.json()["actor"].startswith("oidc-")


def test_production_browser_cookies_are_secure_host_only_and_consistently_deleted() -> None:
    client, provider = _browser_client(
        app_env="production",
        static_auth_enabled=False,
        runner_token="",
        admin_token="",
        rate_limit_secret=(
            "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"
        ),
        cors_origins=["https://testserver"],
        oidc_redirect_uri="https://testserver/api/v1/auth/callback",
    )

    login = client.get("/api/v1/auth/login", follow_redirects=False)
    query = parse_qs(urlsplit(login.headers["Location"]).query)
    provider.nonce = query["nonce"][0]
    callback = client.get(
        "/api/v1/auth/callback",
        params={"code": "one-time-code", "state": query["state"][0]},
        follow_redirects=False,
    )

    assert "Secure" in login.headers["Set-Cookie"]
    assert "Domain=" not in login.headers["Set-Cookie"]
    assert callback.status_code == 302
    assert "incidentlens_session=" in callback.headers["Set-Cookie"]
    assert "Secure" in callback.headers["Set-Cookie"]
    assert "Domain=" not in callback.headers["Set-Cookie"]
    assert "Max-Age=0" in callback.headers["Set-Cookie"]


def test_cookie_session_requires_csrf_header_and_never_masks_invalid_bearer() -> None:
    client, provider = _browser_client()
    _sign_in(client, provider)
    payload = {
        "incident_case_id": "deploy-timeout-showcase",
        "mode": "replay",
    }

    missing_csrf = client.post("/api/v1/investigations", json=payload)
    created = client.post(
        "/api/v1/investigations",
        headers={"X-IncidentLens-CSRF": "1"},
        json=payload,
    )
    invalid_bearer = client.get(
        "/api/v1/investigations",
        headers={"Authorization": "Bearer invalid-even-with-session"},
    )

    assert missing_csrf.status_code == 403
    assert missing_csrf.json() == {"detail": "CSRF validation failed"}
    assert missing_csrf.headers["Cache-Control"] == "no-store"
    assert created.status_code == 202
    assert invalid_bearer.status_code == 403
    assert invalid_bearer.json() == {"detail": "Invalid credential"}


def test_logout_revokes_the_server_session_and_clears_the_cookie() -> None:
    client, provider = _browser_client()
    _sign_in(client, provider)

    blocked = client.post("/api/v1/auth/logout")
    logged_out = client.post(
        "/api/v1/auth/logout",
        headers={"X-IncidentLens-CSRF": "1"},
    )
    session = client.get("/api/v1/auth/session")

    assert blocked.status_code == 403
    assert logged_out.status_code == 204
    assert "incidentlens_session=" in logged_out.headers["Set-Cookie"]
    assert "Max-Age=0" in logged_out.headers["Set-Cookie"]
    assert session.json()["authenticated"] is False


def test_browser_login_does_not_allow_an_external_return_redirect() -> None:
    client, provider = _browser_client()
    callback = _sign_in(
        client,
        provider,
        return_to="https://attacker.example.com/steal",
    )

    assert callback.headers["Location"] == "/"


def test_browser_login_start_is_durably_rate_limited_per_client() -> None:
    client, _provider = _browser_client(
        oidc_login_rate_limit=2,
        oidc_login_rate_window_seconds=60,
    )

    first = client.get("/api/v1/auth/login", follow_redirects=False)
    second = client.get("/api/v1/auth/login", follow_redirects=False)
    blocked = client.get("/api/v1/auth/login", follow_redirects=False)

    assert first.status_code == 302
    assert second.status_code == 302
    assert blocked.status_code == 429
    assert blocked.json() == {"detail": "Too many login attempts"}
    assert 1 <= int(blocked.headers["Retry-After"]) <= 60


def test_oidc_error_callback_consumes_state_without_calling_the_token_endpoint() -> None:
    client, provider = _browser_client()
    login = client.get("/api/v1/auth/login", follow_redirects=False)
    query = parse_qs(urlsplit(login.headers["Location"]).query)

    callback = client.get(
        "/api/v1/auth/callback",
        params={
            "error": "access_denied",
            "state": query["state"][0],
        },
        follow_redirects=False,
    )

    assert callback.status_code == 400
    assert callback.json() == {"detail": "OIDC callback validation failed"}
    assert provider.token_calls == 0
    assert "Max-Age=0" in callback.headers["Set-Cookie"]


def test_oidc_callback_secrets_are_redacted_from_access_log_paths() -> None:
    value = redact_access_log_path(
        "/api/v1/auth/callback?code=authorization-secret"
        "&state=browser-secret&error=none"
    )

    assert "authorization-secret" not in value
    assert "browser-secret" not in value
    assert value == (
        "/api/v1/auth/callback?code=[REDACTED]"
        "&state=[REDACTED]&error=none"
    )
