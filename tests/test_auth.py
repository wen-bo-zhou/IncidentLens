from incidentlens import auth
from incidentlens.auth import Principal, principal_from_header
from incidentlens.config import Settings
from starlette.requests import Request


def test_non_ascii_bearer_token_is_treated_as_an_invalid_credential() -> None:
    settings = Settings(_env_file=None)

    principal = principal_from_header("Bearer 无效令牌", settings)

    assert principal.role == "guest"
    assert principal.actor == "guest"


def test_oidc_verifier_can_authenticate_a_non_static_bearer_token() -> None:
    class Verifier:
        def verify(self, token: str) -> Principal | None:
            assert token == "signed-oidc-token"
            return Principal(
                role="runner",
                actor="oidc-6e2977ae-alice",
                token_hash="identity-hash",
            )

    principal = principal_from_header(
        "Bearer signed-oidc-token",
        Settings(_env_file=None),
        oidc_verifier=Verifier(),
    )

    assert principal == Principal(
        role="runner",
        actor="oidc-6e2977ae-alice",
        token_hash="identity-hash",
    )


def test_disabling_static_authentication_rejects_the_legacy_token() -> None:
    settings = Settings(
        static_auth_enabled=False,
        oidc_issuer="https://idp.example.com",
        oidc_audience="incidentlens-api",
        oidc_jwks_url="https://idp.example.com/jwks",
        oidc_runner_groups=["incidentlens-runners"],
        _env_file=None,
    )

    principal = principal_from_header("Bearer runner-demo-token", settings)

    assert principal.role == "guest"


def test_client_ip_uses_forwarding_chain_only_from_a_trusted_proxy() -> None:
    trusted_request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [
                (b"x-forwarded-for", b"198.51.100.23, 10.1.2.3"),
            ],
            "client": ("10.2.3.4", 4321),
        }
    )
    untrusted_request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [
                (b"x-forwarded-for", b"198.51.100.99"),
            ],
            "client": ("203.0.113.17", 4321),
        }
    )

    assert auth.client_ip_from_request(trusted_request, ["10.0.0.0/8"]) == (
        "198.51.100.23"
    )
    assert auth.client_ip_from_request(untrusted_request, ["10.0.0.0/8"]) == (
        "203.0.113.17"
    )


def test_client_ip_rejects_a_malformed_forwarding_chain() -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"x-forwarded-for", b"not-an-ip")],
            "client": ("10.2.3.4", 4321),
        }
    )

    assert auth.client_ip_from_request(request, ["10.0.0.0/8"]) == "10.2.3.4"
