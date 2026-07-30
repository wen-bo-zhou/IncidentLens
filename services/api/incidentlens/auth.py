from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from ipaddress import ip_address, ip_network
from secrets import compare_digest
from typing import Literal, Protocol

from fastapi import Header, HTTPException
from starlette.requests import Request

from incidentlens.config import Settings

Role = Literal["guest", "runner", "admin"]


class AuthenticationUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Principal:
    role: Role
    actor: str
    token_hash: str | None = None


class BearerTokenVerifier(Protocol):
    def verify(self, token: str) -> Principal | None: ...


def client_ip_from_request(
    request: Request,
    trusted_proxy_cidrs: list[str],
) -> str:
    peer_value = request.client.host if request.client is not None else "unknown"
    try:
        peer = ip_address(peer_value)
    except ValueError:
        return "unknown"
    trusted_networks = tuple(
        ip_network(network, strict=True) for network in trusted_proxy_cidrs
    )

    def is_trusted(value: object) -> bool:
        return any(value in network for network in trusted_networks)

    if not is_trusted(peer):
        return peer.compressed
    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return peer.compressed
    values = [item.strip() for item in forwarded.split(",")]
    if not values or len(values) > 20:
        return peer.compressed
    try:
        forwarded_addresses = [ip_address(item) for item in values]
    except ValueError:
        return peer.compressed
    current = peer
    for address in reversed(forwarded_addresses):
        if not is_trusted(current):
            break
        current = address
    return current.compressed


def principal_from_header(
    authorization: str | None,
    settings: Settings,
    *,
    oidc_verifier: BearerTokenVerifier | None = None,
) -> Principal:
    if not authorization or not authorization.startswith("Bearer "):
        return Principal(role="guest", actor="guest")
    token = authorization.removeprefix("Bearer ").strip()
    for role in ("admin", "runner"):
        for actor, expected in settings.credentials_for(role):
            if compare_digest(
                token.encode("utf-8"),
                expected.encode("utf-8"),
            ):
                return Principal(
                    role=role,
                    actor=actor,
                    token_hash=sha256(token.encode("utf-8")).hexdigest(),
                )
    if oidc_verifier is not None:
        principal = oidc_verifier.verify(token)
        if principal is not None:
            return principal
    return Principal(role="guest", actor="guest")


def principal_from_request(
    request: Request,
    authorization: str | None,
    settings: Settings,
    *,
    oidc_verifier: BearerTokenVerifier | None = None,
) -> Principal:
    cached = getattr(request.state, "principal", None)
    if isinstance(cached, Principal):
        return cached
    return principal_from_header(
        authorization,
        settings,
        oidc_verifier=oidc_verifier,
    )


def require_role(
    settings: Settings,
    *allowed: Role,
    oidc_verifier: BearerTokenVerifier | None = None,
) -> Callable[..., Principal]:
    def dependency(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> Principal:
        try:
            principal = principal_from_request(
                request,
                authorization,
                settings,
                oidc_verifier=oidc_verifier,
            )
        except AuthenticationUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail="Authentication service unavailable",
                headers={"Retry-After": "30"},
            ) from exc
        if principal.role not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return principal

    return dependency
