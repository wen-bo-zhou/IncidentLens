from incidentlens.auth import principal_from_header
from incidentlens.config import Settings


def test_non_ascii_bearer_token_is_treated_as_an_invalid_credential() -> None:
    settings = Settings(_env_file=None)

    principal = principal_from_header("Bearer 无效令牌", settings)

    assert principal.role == "guest"
    assert principal.actor == "guest"
