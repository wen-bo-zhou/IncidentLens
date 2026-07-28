from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from secrets import compare_digest
from typing import Literal

from fastapi import Header, HTTPException

from incidentlens.config import Settings

Role = Literal["guest", "runner", "admin"]


@dataclass(frozen=True)
class Principal:
    role: Role
    actor: str
    token_hash: str | None = None


def principal_from_header(
    authorization: str | None, settings: Settings
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
    return Principal(role="guest", actor="guest")


def require_role(
    settings: Settings, *allowed: Role
) -> Callable[[str | None], Principal]:
    def dependency(
        authorization: str | None = Header(default=None),
    ) -> Principal:
        principal = principal_from_header(authorization, settings)
        if principal.role not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return principal

    return dependency
