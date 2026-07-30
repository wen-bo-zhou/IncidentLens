from __future__ import annotations

import json
from base64 import b64encode, urlsafe_b64encode
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from secrets import token_urlsafe
from time import monotonic
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from incidentlens.auth import AuthenticationUnavailable, Principal
from incidentlens.config import Settings
from incidentlens.oidc import OidcTokenVerifier

_MAX_TOKEN_RESPONSE_BYTES = 1_000_000
_MAX_TOKEN_BYTES = 16_384
_MAX_TOKEN_RESPONSE_JSON_DEPTH = 64
_TOKEN_RESPONSE_TOTAL_DEADLINE_SECONDS = 5.0


def _json_nesting_is_bounded(document: bytes | bytearray) -> bool:
    depth = 0
    in_string = False
    escaped = False
    for value in document:
        if in_string:
            if escaped:
                escaped = False
            elif value == ord("\\"):
                escaped = True
            elif value == ord('"'):
                in_string = False
            continue
        if value == ord('"'):
            in_string = True
        elif value in (ord("{"), ord("[")):
            depth += 1
            if depth > _MAX_TOKEN_RESPONSE_JSON_DEPTH:
                return False
        elif value in (ord("}"), ord("]")):
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and not in_string


class OidcExchangeError(ValueError):
    pass


@dataclass(frozen=True)
class BrowserAuthorizationStart:
    authorization_url: str
    state: str
    browser_token: str
    code_verifier: str
    nonce: str


@dataclass(frozen=True)
class BrowserIdentity:
    principal: Principal
    expires_at: datetime


class OidcBrowserClient:
    def __init__(
        self,
        settings: Settings,
        verifier: OidcTokenVerifier,
        *,
        http_client: httpx.Client | None = None,
        deadline_clock: Callable[[], float] | None = None,
    ) -> None:
        if not settings.oidc_browser_enabled:
            raise ValueError("OIDC browser client requires complete configuration")
        self.settings = settings
        self.verifier = verifier
        self._http_client = http_client or httpx.Client(
            timeout=httpx.Timeout(connect=3.0, read=0.25, write=3.0, pool=3.0),
            follow_redirects=False,
        )
        self._owns_http_client = http_client is None
        self._deadline_clock = deadline_clock or monotonic

    def close(self) -> None:
        if self._owns_http_client:
            self._http_client.close()

    def begin_authorization(self) -> BrowserAuthorizationStart:
        state = token_urlsafe(32)
        browser_token = token_urlsafe(32)
        code_verifier = token_urlsafe(64)
        nonce = token_urlsafe(32)
        challenge = (
            urlsafe_b64encode(sha256(code_verifier.encode()).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        authorization_url = (
            f"{self.settings.oidc_authorization_url}?"
            + urlencode(
                {
                    "response_type": "code",
                    "client_id": self.settings.oidc_client_id,
                    "redirect_uri": self.settings.oidc_redirect_uri,
                    "scope": " ".join(self.settings.oidc_scopes),
                    "state": state,
                    "nonce": nonce,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                }
            )
        )
        return BrowserAuthorizationStart(
            authorization_url=authorization_url,
            state=state,
            browser_token=browser_token,
            code_verifier=code_verifier,
            nonce=nonce,
        )

    def exchange_code(
        self,
        *,
        code: str,
        code_verifier: str,
        nonce: str,
    ) -> BrowserIdentity:
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.settings.oidc_redirect_uri,
            "code_verifier": code_verifier,
        }
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        }
        client_secret = self.settings.oidc_client_secret.get_secret_value()
        if client_secret:
            encoded_client = quote(self.settings.oidc_client_id, safe="")
            encoded_secret = quote(client_secret, safe="")
            credentials = b64encode(
                f"{encoded_client}:{encoded_secret}".encode()
            ).decode("ascii")
            headers["Authorization"] = f"Basic {credentials}"
        else:
            form["client_id"] = self.settings.oidc_client_id
        payload = self._token_request(form, headers)
        access_token = payload.get("access_token")
        id_token = payload.get("id_token")
        token_type = payload.get("token_type")
        if (
            not isinstance(access_token, str)
            or not 1 <= len(access_token.encode()) <= _MAX_TOKEN_BYTES
            or not isinstance(id_token, str)
            or not 1 <= len(id_token.encode()) <= _MAX_TOKEN_BYTES
            or not isinstance(token_type, str)
            or token_type.lower() != "bearer"
        ):
            raise OidcExchangeError("OIDC token response is invalid")
        verified_access = self.verifier.verify_for_session(access_token)
        if verified_access is None:
            raise OidcExchangeError("OIDC access token is invalid")
        verified_id = self.verifier.verify_id_token(
            id_token,
            nonce=nonce,
            access_token=access_token,
            expected_subject=verified_access.subject,
        )
        if verified_id is None:
            raise OidcExchangeError("OIDC ID token is invalid")
        return BrowserIdentity(
            principal=verified_access.principal,
            expires_at=min(
                verified_access.expires_at,
                verified_id.expires_at,
            ),
        )

    def _token_request(
        self,
        form: dict[str, str],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        started_at = self._deadline_clock()
        try:
            response_context = self._http_client.stream(
                "POST",
                self.settings.oidc_token_url,
                data=form,
                headers=headers,
            )
            with response_context as response:
                if self._deadline_exceeded(started_at):
                    raise AuthenticationUnavailable
                if response.status_code >= 500 or response.status_code == 429:
                    raise AuthenticationUnavailable
                if not response.is_success:
                    raise OidcExchangeError(
                        "OIDC authorization code was rejected"
                    )
                if (
                    response.headers.get("Content-Encoding", "identity")
                    .lower()
                    .strip()
                    not in {"", "identity"}
                ):
                    raise AuthenticationUnavailable
                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        if int(content_length) > _MAX_TOKEN_RESPONSE_BYTES:
                            raise AuthenticationUnavailable
                    except ValueError as exc:
                        raise AuthenticationUnavailable from exc
                content = bytearray()
                for chunk in response.iter_raw():
                    if (
                        self._deadline_exceeded(started_at)
                        or len(content) + len(chunk)
                        > _MAX_TOKEN_RESPONSE_BYTES
                    ):
                        raise AuthenticationUnavailable
                    content.extend(chunk)
                if self._deadline_exceeded(started_at):
                    raise AuthenticationUnavailable
        except httpx.HTTPError as exc:
            raise AuthenticationUnavailable from exc
        if not _json_nesting_is_bounded(content):
            raise AuthenticationUnavailable
        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, RecursionError, UnicodeDecodeError) as exc:
            raise AuthenticationUnavailable from exc
        if not isinstance(payload, dict):
            raise AuthenticationUnavailable
        return payload

    def _deadline_exceeded(self, started_at: float) -> bool:
        return (
            self._deadline_clock() - started_at
            > _TOKEN_RESPONSE_TOTAL_DEADLINE_SECONDS
        )
