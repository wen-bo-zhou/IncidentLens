import re
from base64 import urlsafe_b64decode
from binascii import Error as Base64DecodeError
from functools import lru_cache
from ipaddress import ip_network
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

CredentialRole = Literal["runner", "admin"]
_RESERVED_OIDC_ROLE_CLAIMS = {
    "acr",
    "amr",
    "aud",
    "auth_time",
    "azp",
    "client_id",
    "exp",
    "iat",
    "iss",
    "jti",
    "nbf",
    "nonce",
    "scope",
    "sid",
    "sub",
}


def _is_strong_rate_limit_secret(value: str) -> bool:
    if re.fullmatch(r"[A-Za-z0-9_-]{43,}", value) is None:
        return False
    try:
        decoded = urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (Base64DecodeError, ValueError):
        return False
    return len(decoded) >= 32 and len(set(value)) >= 12


class Settings(BaseSettings):
    app_name: str = "IncidentLens API"
    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///data/runtime/incidentlens.db"
    redis_url: str = "redis://localhost:6379/0"
    task_mode: str = "inline"
    model_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model_api_key: str = ""
    model_name: str = "qwen-plus"
    max_cost_cny: float = 0.20
    runner_daily_limit: int = 10
    auth_failure_limit: int = Field(default=10, ge=1, le=1000)
    auth_failure_window_seconds: int = Field(default=300, ge=10, le=86400)
    rate_limit_max_records: int = Field(default=10000, ge=1, le=1000000)
    rate_limit_secret: SecretStr = SecretStr(
        "incidentlens-development-rate-limit-secret"
    )
    trusted_proxy_cidrs: list[str] = Field(
        default_factory=lambda: ["127.0.0.0/8", "::1/128"]
    )
    static_auth_enabled: bool = True
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_jwks_url: str = ""
    oidc_groups_claim: str = "groups"
    oidc_runner_groups: list[str] = Field(default_factory=list)
    oidc_admin_groups: list[str] = Field(default_factory=list)
    oidc_authorization_url: str = ""
    oidc_token_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: SecretStr = SecretStr("")
    oidc_redirect_uri: str = ""
    oidc_scopes: list[str] = Field(default_factory=lambda: ["openid"])
    oidc_login_ttl_seconds: int = Field(default=600, ge=60, le=900)
    oidc_login_rate_limit: int = Field(default=10, ge=1, le=1000)
    oidc_login_rate_window_seconds: int = Field(default=60, ge=10, le=3600)
    oidc_login_max_outstanding: int = Field(default=5000, ge=1, le=100000)
    oidc_login_max_outstanding_per_client: int = Field(
        default=10,
        ge=1,
        le=1000,
    )
    oidc_session_ttl_seconds: int = Field(default=28800, ge=300, le=86400)
    runner_token: SecretStr = SecretStr("runner-demo-token")
    admin_token: SecretStr = SecretStr("admin-demo-token")
    runner_credentials: dict[str, SecretStr] = Field(default_factory=dict)
    admin_credentials: dict[str, SecretStr] = Field(default_factory=dict)
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("runner_credentials", "admin_credentials")
    @classmethod
    def validate_credential_actors(
        cls, value: dict[str, SecretStr]
    ) -> dict[str, SecretStr]:
        for actor in value:
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._@-]{0,63}", actor) is None:
                raise ValueError(
                    "Named credential actor must use 1-64 safe identifier characters"
                )
            if actor.startswith("oidc-"):
                raise ValueError("The oidc- actor namespace is reserved")
        return value

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: list[str]) -> list[str]:
        if not value or "*" in value:
            raise ValueError(
                "Credentialed requests cannot use an empty or wildcard CORS allowlist"
            )
        for origin in value:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("CORS entries must be exact HTTP origins")
        return value

    @field_validator("trusted_proxy_cidrs")
    @classmethod
    def validate_trusted_proxy_cidrs(cls, value: list[str]) -> list[str]:
        for network in value:
            try:
                ip_network(network, strict=True)
            except ValueError as exc:
                raise ValueError("Trusted proxies must be valid CIDR networks") from exc
        return value

    @field_validator("oidc_groups_claim")
    @classmethod
    def validate_oidc_claim_names(cls, value: str) -> str:
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}", value) is None:
            raise ValueError("OIDC claim names must be safe top-level identifiers")
        if value in _RESERVED_OIDC_ROLE_CLAIMS:
            raise ValueError(
                "OIDC security claims cannot be used for role mapping"
            )
        return value

    @field_validator("oidc_runner_groups", "oidc_admin_groups")
    @classmethod
    def validate_oidc_groups(cls, value: list[str]) -> list[str]:
        if any(not group.strip() or len(group) > 128 for group in value):
            raise ValueError("OIDC role groups must contain 1-128 characters")
        if len(value) != len(set(value)):
            raise ValueError("OIDC role groups cannot contain duplicates")
        return value

    @field_validator("oidc_scopes")
    @classmethod
    def validate_oidc_scopes(cls, value: list[str]) -> list[str]:
        if (
            not value
            or len(value) > 20
            or len(value) != len(set(value))
            or any(
                re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", scope) is None
                for scope in value
            )
        ):
            raise ValueError("OIDC scopes must be unique safe scope names")
        if "openid" not in value:
            raise ValueError("Browser OIDC scopes must include openid")
        if "offline_access" in value:
            raise ValueError(
                "Browser OIDC cannot request offline_access without refresh-token storage"
            )
        return value

    @model_validator(mode="after")
    def validate_authentication(self) -> Self:
        oidc_endpoints = (
            self.oidc_issuer,
            self.oidc_audience,
            self.oidc_jwks_url,
        )
        oidc_configured = any(
            (
                *oidc_endpoints,
                *self.oidc_runner_groups,
                *self.oidc_admin_groups,
            )
        )
        if oidc_configured and not all(oidc_endpoints):
            raise ValueError(
                "OIDC issuer, audience and JWKS URL must be configured together"
            )
        if self.oidc_enabled:
            if not self.oidc_runner_groups and not self.oidc_admin_groups:
                raise ValueError("OIDC requires at least one role group mapping")
            if set(self.oidc_runner_groups) & set(self.oidc_admin_groups):
                raise ValueError("OIDC Runner and Admin role groups cannot overlap")
            for endpoint in (self.oidc_issuer, self.oidc_jwks_url):
                parsed = urlsplit(endpoint)
                if (
                    parsed.scheme not in {"http", "https"}
                    or not parsed.netloc
                    or parsed.username is not None
                    or parsed.password is not None
                    or parsed.query
                    or parsed.fragment
                ):
                    raise ValueError("OIDC endpoints must be absolute HTTP URLs")
                if self.app_env == "production" and parsed.scheme != "https":
                    raise ValueError("Production OIDC endpoints must use HTTPS")

        browser_fields = (
            self.oidc_authorization_url,
            self.oidc_token_url,
            self.oidc_client_id,
            self.oidc_redirect_uri,
        )
        browser_configured = any(
            (
                *browser_fields,
                self.oidc_client_secret.get_secret_value(),
            )
        )
        if browser_configured and not all(browser_fields):
            raise ValueError(
                "OIDC browser client authorization URL, token URL, client ID "
                "and redirect URI must be configured together"
            )
        if self.oidc_browser_enabled:
            if not self.oidc_enabled:
                raise ValueError("OIDC browser client requires OIDC token validation")
            if (
                self.oidc_login_max_outstanding_per_client
                > self.oidc_login_max_outstanding
            ):
                raise ValueError(
                    "OIDC per-client pending login limit cannot exceed "
                    "the global pending login limit"
                )
            for endpoint in (
                self.oidc_authorization_url,
                self.oidc_token_url,
            ):
                parsed = urlsplit(endpoint)
                if (
                    parsed.scheme not in {"http", "https"}
                    or not parsed.netloc
                    or parsed.username is not None
                    or parsed.password is not None
                    or parsed.query
                    or parsed.fragment
                ):
                    raise ValueError(
                        "OIDC browser endpoints must be absolute HTTP URLs"
                    )
                if self.app_env == "production" and parsed.scheme != "https":
                    raise ValueError(
                        "Production OIDC browser endpoints must use HTTPS"
                    )
            redirect = urlsplit(self.oidc_redirect_uri)
            if (
                redirect.scheme not in {"http", "https"}
                or not redirect.netloc
                or redirect.username is not None
                or redirect.password is not None
                or redirect.query
                or redirect.fragment
            ):
                raise ValueError(
                    "OIDC redirect URI must be an absolute URL without query or fragment"
                )
            if self.app_env == "production":
                if redirect.scheme != "https":
                    raise ValueError(
                        "Production OIDC browser endpoints must use HTTPS"
                    )
                if not self.oidc_client_secret.get_secret_value():
                    raise ValueError(
                        "Production OIDC browser client requires a client secret"
                    )
        if not self.static_auth_enabled and not self.oidc_enabled:
            raise ValueError("Disabling static authentication requires OIDC")

        values: list[str] = []
        if self.static_auth_enabled:
            runner = self.credentials_for("runner")
            admin = self.credentials_for("admin")
            if {actor for actor, _token in runner} & {
                actor for actor, _token in admin
            }:
                raise ValueError("Credential actor names must be unique across roles")
            values = [token for _actor, token in (*runner, *admin)]
            if any(not token for token in values):
                raise ValueError("Configured credentials cannot be empty")
            if len(values) != len(set(values)):
                raise ValueError("Every configured credential must be unique")
        if self.app_env == "production":
            if self.static_auth_enabled and {
                "runner-demo-token",
                "admin-demo-token",
            } & set(values):
                raise ValueError("Production cannot use demo credentials")
            if self.static_auth_enabled and any(len(token) < 32 for token in values):
                raise ValueError(
                    "Production credentials must contain at least 32 characters"
                )
            rate_limit_secret = self.rate_limit_secret.get_secret_value()
            if (
                rate_limit_secret == "incidentlens-development-rate-limit-secret"
                or not _is_strong_rate_limit_secret(rate_limit_secret)
            ):
                raise ValueError(
                    "Production rate-limit secret must encode at least 32 random "
                    "bytes as unpadded base64url"
                )
        return self

    @property
    def oidc_enabled(self) -> bool:
        return bool(self.oidc_issuer and self.oidc_audience and self.oidc_jwks_url)

    @property
    def oidc_browser_enabled(self) -> bool:
        return bool(
            self.oidc_authorization_url
            and self.oidc_token_url
            and self.oidc_client_id
            and self.oidc_redirect_uri
        )

    def credentials_for(
        self, role: CredentialRole
    ) -> tuple[tuple[str, str], ...]:
        if not self.static_auth_enabled:
            return ()
        configured = (
            self.runner_credentials
            if role == "runner"
            else self.admin_credentials
        )
        if configured:
            return tuple(
                (actor, secret.get_secret_value())
                for actor, secret in configured.items()
            )
        fallback = self.runner_token if role == "runner" else self.admin_token
        return ((role, fallback.get_secret_value()),)


@lru_cache
def get_settings() -> Settings:
    return Settings()
