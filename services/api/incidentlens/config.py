import re
from functools import lru_cache
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

CredentialRole = Literal["runner", "admin"]


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

    @model_validator(mode="after")
    def validate_credentials(self) -> Self:
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
            if {"runner-demo-token", "admin-demo-token"} & set(values):
                raise ValueError("Production cannot use demo credentials")
            if any(len(token) < 32 for token in values):
                raise ValueError(
                    "Production credentials must contain at least 32 characters"
                )
        return self

    def credentials_for(
        self, role: CredentialRole
    ) -> tuple[tuple[str, str], ...]:
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
