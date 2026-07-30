import pytest
from incidentlens.config import Settings
from pydantic import ValidationError


def _production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "production",
        "runner_credentials": {
            "oncall-primary": "runner-production-token-000000000001"
        },
        "admin_credentials": {
            "security-lead": "admin-production-token-000000000001"
        },
        "rate_limit_secret": "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8",
        "cors_origins": ["https://incidentlens.example.com"],
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_production_rejects_demo_credentials() -> None:
    with pytest.raises(ValidationError, match="demo credentials"):
        Settings(app_env="production", _env_file=None)


def test_empty_credentials_are_rejected_in_every_environment() -> None:
    with pytest.raises(ValidationError, match="cannot be empty"):
        Settings(runner_token="", _env_file=None)


def test_production_rejects_short_credentials() -> None:
    with pytest.raises(ValidationError, match="at least 32 characters"):
        _production_settings(runner_credentials={"oncall-primary": "too-short"})


def test_production_rejects_credentials_shared_across_roles() -> None:
    shared = "shared-production-token-000000000001"

    with pytest.raises(ValidationError, match="unique"):
        _production_settings(
            runner_credentials={"oncall-primary": shared},
            admin_credentials={"security-lead": shared},
        )


@pytest.mark.parametrize(
    "secret",
    [
        "too-short",
        "0" * 64,
        " " * 43,
        "incidentlens-development-rate-limit-secret",
    ],
)
def test_production_rejects_a_weak_rate_limit_secret(secret: str) -> None:
    with pytest.raises(ValidationError, match="rate-limit secret"):
        _production_settings(rate_limit_secret=secret)


def test_trusted_proxies_must_be_strict_cidr_networks() -> None:
    with pytest.raises(ValidationError, match="valid CIDR networks"):
        Settings(trusted_proxy_cidrs=["127.0.0.1/24"], _env_file=None)


def test_named_actor_identity_cannot_be_shared_across_roles() -> None:
    with pytest.raises(ValidationError, match="actor names must be unique"):
        _production_settings(
            runner_credentials={
                "shared-actor": "runner-production-token-000000000001"
            },
            admin_credentials={
                "shared-actor": "admin-production-token-000000000001"
            },
        )


def test_production_rejects_wildcard_cors_with_credentials() -> None:
    with pytest.raises(ValidationError, match="wildcard CORS"):
        _production_settings(cors_origins=["*"])


def test_credentials_require_a_safe_audit_actor_name() -> None:
    with pytest.raises(ValidationError, match="credential actor"):
        _production_settings(
            runner_credentials={
                "oncall primary": "runner-production-token-000000000001"
            }
        )


@pytest.mark.parametrize(
    "origin",
    [
        "https://incidentlens.example.com/console",
        "https://incidentlens.example.com/",
    ],
)
def test_cors_origins_must_be_exact_http_origins(origin: str) -> None:
    with pytest.raises(ValidationError, match="exact HTTP origins"):
        _production_settings(cors_origins=[origin])


def test_production_accepts_named_strong_credentials_and_exact_origins() -> None:
    settings = _production_settings()

    assert list(settings.runner_credentials) == ["oncall-primary"]
    assert list(settings.admin_credentials) == ["security-lead"]
    assert settings.cors_origins == ["https://incidentlens.example.com"]
