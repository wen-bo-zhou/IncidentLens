from collections.abc import Callable
from typing import Literal

from fastapi import Header, HTTPException

from incidentlens.config import Settings

Role = Literal["guest", "runner", "admin"]


def role_from_header(authorization: str | None, settings: Settings) -> Role:
    if not authorization or not authorization.startswith("Bearer "):
        return "guest"
    token = authorization.removeprefix("Bearer ").strip()
    if token == settings.admin_token:
        return "admin"
    if token == settings.runner_token:
        return "runner"
    return "guest"


def require_role(settings: Settings, *allowed: Role) -> Callable[[str | None], Role]:
    def dependency(authorization: str | None = Header(default=None)) -> Role:
        role = role_from_header(authorization, settings)
        if role not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return role

    return dependency
