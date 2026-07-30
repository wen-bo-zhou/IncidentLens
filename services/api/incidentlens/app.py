from __future__ import annotations

import asyncio
import hmac
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Annotated, Literal

from fastapi import (
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, model_validator
from redis import Redis
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import run_in_threadpool
from starlette.responses import RedirectResponse

from incidentlens.auth import (
    AuthenticationUnavailable,
    BearerTokenVerifier,
    Principal,
    client_ip_from_request,
    principal_from_header,
    principal_from_request,
    require_role,
)
from incidentlens.config import Settings, get_settings
from incidentlens.db import InvestigationStore, create_session_factory
from incidentlens.evals import EvaluationRunner
from incidentlens.model_client import build_model_client
from incidentlens.observability import configure_observability
from incidentlens.oidc import OidcTokenVerifier
from incidentlens.oidc_browser import OidcBrowserClient, OidcExchangeError
from incidentlens.scenarios import ScenarioRepository
from incidentlens.schemas import IncidentCase
from incidentlens.workflow import InvestigationEngine

_OIDC_TRANSACTION_COOKIE = "incidentlens_oidc_transaction"
_SESSION_COOKIE = "incidentlens_session"
_CSRF_HEADER = "x-incidentlens-csrf"
_SAFE_RETURN_PATHS = {"/", "/operations", "/evaluations"}
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class InvestigationCreate(BaseModel):
    incident_case_id: str
    mode: Literal["live", "replay"] = "live"
    start_at: datetime | None = None
    end_at: datetime | None = None

    @model_validator(mode="after")
    def validate_time_window(self) -> InvestigationCreate:
        for value in (self.start_at, self.end_at):
            if value is not None and value.utcoffset() is None:
                raise ValueError("Investigation time window must include a timezone")
        if (
            self.start_at is not None
            and self.end_at is not None
            and self.start_at >= self.end_at
        ):
            raise ValueError("Investigation start_at must be earlier than end_at")
        return self


class StreamTicket(BaseModel):
    ticket: str
    expires_at: datetime


def create_app(
    *,
    testing: bool = False,
    settings: Settings | None = None,
    oidc_verifier: BearerTokenVerifier | None = None,
    oidc_browser_client: OidcBrowserClient | None = None,
) -> FastAPI:
    if settings is None:
        settings = (
            Settings(
                app_env="test",
                database_url="sqlite://",
                task_mode="inline",
            )
            if testing
            else get_settings()
        )
    elif testing:
        settings = settings.model_copy(
            update={"database_url": "sqlite://", "task_mode": "inline"}
        )
    repository = ScenarioRepository.seeded()
    public_cases = repository.list_cases()
    public_case_ids = {case.id for case in public_cases}
    persisted_case_ids: set[str] = set()
    session_factory = create_session_factory(settings.database_url, testing=testing)
    store = InvestigationStore(session_factory)
    for persisted_case in store.list_incidents():
        repository.add_case(persisted_case)
        persisted_case_ids.add(persisted_case.id)
    engine = InvestigationEngine(
        model_client=build_model_client(
            base_url=settings.model_base_url,
            api_key=settings.model_api_key,
            model=settings.model_name,
            max_cost_cny=settings.max_cost_cny,
        )
    )
    replay_engine = InvestigationEngine()
    replay_cache = {
        case.id: replay_engine.run(
            case, investigation_id=f"replay-{case.id}"
        ).report.model_dump(mode="json")
        for case in public_cases
    }
    active_oidc_verifier = oidc_verifier
    owned_oidc_verifier: OidcTokenVerifier | None = None
    if active_oidc_verifier is None and settings.oidc_enabled:
        owned_oidc_verifier = OidcTokenVerifier(settings)
        active_oidc_verifier = owned_oidc_verifier
    active_oidc_browser_client = oidc_browser_client
    owned_oidc_browser_client: OidcBrowserClient | None = None
    if active_oidc_browser_client is None and settings.oidc_browser_enabled:
        if not isinstance(active_oidc_verifier, OidcTokenVerifier):
            raise ValueError(
                "Browser OIDC requires the full OIDC token verifier"
            )
        owned_oidc_browser_client = OidcBrowserClient(
            settings,
            active_oidc_verifier,
        )
        active_oidc_browser_client = owned_oidc_browser_client
    app = FastAPI(
        title="IncidentLens API",
        version="0.9.0",
        description="Evidence-first production incident investigation assistant",
    )
    app.state.repository = repository
    app.state.store = store
    app.state.settings = settings
    app.state.replay_cache = replay_cache
    app.state.oidc_verifier = active_oidc_verifier
    app.state.oidc_browser_client = active_oidc_browser_client
    if owned_oidc_verifier is not None:
        app.router.add_event_handler("shutdown", owned_oidc_verifier.close)
    if owned_oidc_browser_client is not None:
        app.router.add_event_handler(
            "shutdown",
            owned_oidc_browser_client.close,
        )

    @app.middleware("http")
    async def throttle_invalid_credentials(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        authorization = request.headers.get("authorization")
        principal = Principal(role="guest", actor="guest")
        authentication_source: str | None = None
        if authorization is not None:
            try:
                principal = await run_in_threadpool(
                    principal_from_header,
                    authorization,
                    settings,
                    oidc_verifier=active_oidc_verifier,
                )
            except AuthenticationUnavailable:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Authentication service unavailable"},
                    headers={"Retry-After": "30"},
                )
            request.state.principal = principal
            authentication_source = "bearer"
            if principal.role == "guest":
                client_ip = client_ip_from_request(
                    request,
                    settings.trusted_proxy_cidrs,
                )
                subject_hash = hmac.new(
                    settings.rate_limit_secret.get_secret_value().encode(),
                    f"auth-failure:{client_ip}".encode(),
                    sha256,
                ).hexdigest()
                allowed, retry_after = await run_in_threadpool(
                    store.consume_auth_failure,
                    subject_hash,
                    now=datetime.now(UTC),
                    window_seconds=settings.auth_failure_window_seconds,
                    limit=settings.auth_failure_limit,
                    max_records=settings.rate_limit_max_records,
                )
                if not allowed:
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Too many authentication failures"},
                        headers={"Retry-After": str(retry_after)},
                    )
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Invalid credential"},
                )
        else:
            session_token = request.cookies.get(_SESSION_COOKIE)
            if session_token is not None and len(session_token) <= 128:
                session_principal = await run_in_threadpool(
                    store.authenticate_browser_session,
                    session_token,
                    now=datetime.now(UTC),
                )
                principal = session_principal or Principal(
                    role="guest",
                    actor="guest",
                )
                if principal.role != "guest":
                    request.state.principal = principal
                    authentication_source = "session"
        request.state.authentication_source = authentication_source
        if (
            authentication_source == "session"
            and request.method in _UNSAFE_METHODS
            and request.headers.get(_CSRF_HEADER) != "1"
        ):
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF validation failed"},
            )
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    telemetry = configure_observability(app)

    runner = require_role(
        settings,
        "runner",
        "admin",
        oidc_verifier=active_oidc_verifier,
    )
    admin = require_role(
        settings,
        "admin",
        oidc_verifier=active_oidc_verifier,
    )

    def catalog_reader(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> Principal:
        principal = principal_from_request(
            request,
            authorization,
            settings,
            oidc_verifier=active_oidc_verifier,
        )
        if authorization is not None and principal.role == "guest":
            raise HTTPException(status_code=403, detail="Invalid credential")
        return principal

    def visible_investigation(
        investigation_id: str,
        principal: Principal,
    ) -> dict[str, object]:
        value = store.get(
            investigation_id,
            owner_actor=None if principal.role == "admin" else principal.actor,
        )
        if value is None:
            raise HTTPException(status_code=404, detail="Investigation not found")
        return value

    def no_store(response: Response) -> None:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["Referrer-Policy"] = "no-referrer"

    def clear_oidc_transaction_cookie(response: Response) -> None:
        response.delete_cookie(
            _OIDC_TRANSACTION_COOKIE,
            path="/api/v1/auth/callback",
            secure=settings.app_env == "production",
            httponly=True,
            samesite="lax",
        )

    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def health_ready() -> dict[str, str]:
        try:
            store.ping()
            if settings.task_mode == "celery":
                Redis.from_url(settings.redis_url, socket_timeout=1).ping()
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail="A required dependency is unavailable"
            ) from exc
        return {"status": "ready"}

    @app.get("/api/v1/auth/session")
    def auth_session(request: Request, response: Response) -> dict[str, object]:
        principal = getattr(
            request.state,
            "principal",
            Principal(role="guest", actor="guest"),
        )
        no_store(response)
        return {
            "authenticated": principal.role != "guest",
            "sso_enabled": settings.oidc_browser_enabled,
            "role": principal.role,
            "actor": principal.actor if principal.role != "guest" else None,
        }

    @app.get("/api/v1/auth/login", include_in_schema=False)
    async def auth_login(
        request: Request,
        return_to: Annotated[str, Query(max_length=200)] = "/",
    ) -> Response:
        if active_oidc_browser_client is None:
            raise HTTPException(status_code=404, detail="Browser SSO is disabled")
        client_ip = client_ip_from_request(
            request,
            settings.trusted_proxy_cidrs,
        )
        client_hash = hmac.new(
            settings.rate_limit_secret.get_secret_value().encode(),
            f"oidc-login:{client_ip}".encode(),
            sha256,
        ).hexdigest()
        allowed, retry_after = await run_in_threadpool(
            store.consume_auth_failure,
            client_hash,
            now=datetime.now(UTC),
            window_seconds=settings.oidc_login_rate_window_seconds,
            limit=settings.oidc_login_rate_limit,
            max_records=settings.rate_limit_max_records,
        )
        if not allowed:
            response: Response = JSONResponse(
                status_code=429,
                content={"detail": "Too many login attempts"},
                headers={"Retry-After": str(retry_after)},
            )
            no_store(response)
            return response
        safe_return_to = return_to if return_to in _SAFE_RETURN_PATHS else "/"
        started = active_oidc_browser_client.begin_authorization()
        now = datetime.now(UTC)
        admitted = await run_in_threadpool(
            store.create_oidc_login,
            state=started.state,
            browser_token=started.browser_token,
            client_hash=client_hash,
            code_verifier=started.code_verifier,
            nonce=started.nonce,
            return_to=safe_return_to,
            now=now,
            expires_at=now + timedelta(
                seconds=settings.oidc_login_ttl_seconds
            ),
            max_outstanding=settings.oidc_login_max_outstanding,
            max_outstanding_per_client=(
                settings.oidc_login_max_outstanding_per_client
            ),
        )
        if not admitted:
            response = JSONResponse(
                status_code=429,
                content={"detail": "Too many pending login attempts"},
                headers={"Retry-After": "30"},
            )
            no_store(response)
            return response
        response = RedirectResponse(
            started.authorization_url,
            status_code=status.HTTP_302_FOUND,
        )
        response.set_cookie(
            _OIDC_TRANSACTION_COOKIE,
            started.browser_token,
            max_age=settings.oidc_login_ttl_seconds,
            path="/api/v1/auth/callback",
            secure=settings.app_env == "production",
            httponly=True,
            samesite="lax",
        )
        no_store(response)
        return response

    @app.get("/api/v1/auth/callback", include_in_schema=False)
    async def auth_callback(
        request: Request,
        state_value: Annotated[
            str,
            Query(alias="state", min_length=1, max_length=512),
        ],
        code: Annotated[
            str | None,
            Query(min_length=1, max_length=4096),
        ] = None,
        error: Annotated[
            str | None,
            Query(min_length=1, max_length=200),
        ] = None,
    ) -> Response:
        if active_oidc_browser_client is None:
            raise HTTPException(status_code=404, detail="Browser SSO is disabled")
        browser_token = request.cookies.get(_OIDC_TRANSACTION_COOKIE)
        transaction = None
        if browser_token is not None and len(browser_token) <= 128:
            transaction = await run_in_threadpool(
                store.consume_oidc_login,
                state=state_value,
                browser_token=browser_token,
                now=datetime.now(UTC),
            )
        if transaction is None:
            response: Response = JSONResponse(
                status_code=400,
                content={"detail": "OIDC login transaction is invalid or expired"},
            )
            clear_oidc_transaction_cookie(response)
            no_store(response)
            return response
        if error is not None or code is None:
            response = JSONResponse(
                status_code=400,
                content={"detail": "OIDC callback validation failed"},
            )
            clear_oidc_transaction_cookie(response)
            no_store(response)
            return response
        try:
            identity = await run_in_threadpool(
                active_oidc_browser_client.exchange_code,
                code=code,
                code_verifier=transaction["code_verifier"],
                nonce=transaction["nonce"],
            )
        except AuthenticationUnavailable:
            response = JSONResponse(
                status_code=503,
                content={"detail": "Authentication service unavailable"},
                headers={"Retry-After": "30"},
            )
            clear_oidc_transaction_cookie(response)
            no_store(response)
            return response
        except OidcExchangeError:
            response = JSONResponse(
                status_code=400,
                content={"detail": "OIDC callback validation failed"},
            )
            clear_oidc_transaction_cookie(response)
            no_store(response)
            return response
        now = datetime.now(UTC)
        expires_at = min(
            identity.expires_at,
            now + timedelta(seconds=settings.oidc_session_ttl_seconds),
        )
        if expires_at <= now:
            response = JSONResponse(
                status_code=400,
                content={"detail": "OIDC callback validation failed"},
            )
            clear_oidc_transaction_cookie(response)
            no_store(response)
            return response
        session_token = await run_in_threadpool(
            store.create_browser_session,
            identity.principal,
            now=now,
            expires_at=expires_at,
        )
        return_to = transaction["return_to"]
        if return_to not in _SAFE_RETURN_PATHS:
            return_to = "/"
        response = RedirectResponse(
            return_to,
            status_code=status.HTTP_302_FOUND,
        )
        response.set_cookie(
            _SESSION_COOKIE,
            session_token,
            max_age=max(1, int((expires_at - now).total_seconds())),
            path="/",
            secure=settings.app_env == "production",
            httponly=True,
            samesite="strict",
        )
        clear_oidc_transaction_cookie(response)
        no_store(response)
        store.record_audit(
            actor=identity.principal.actor,
            action="auth.session_created",
            resource_id=identity.principal.actor,
            detail={"role": identity.principal.role},
        )
        return response

    @app.post(
        "/api/v1/auth/logout",
        status_code=status.HTTP_204_NO_CONTENT,
        include_in_schema=False,
    )
    async def auth_logout(request: Request) -> Response:
        session_token = request.cookies.get(_SESSION_COOKIE)
        if session_token is not None and len(session_token) <= 128:
            await run_in_threadpool(
                store.revoke_browser_session,
                session_token,
            )
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(
            _SESSION_COOKIE,
            path="/",
            secure=settings.app_env == "production",
            httponly=True,
            samesite="strict",
        )
        no_store(response)
        return response

    @app.get("/api/v1/incidents")
    def list_incidents(
        principal: Principal = Depends(catalog_reader),
    ) -> list[dict[str, object]]:
        case_ids = [case.id for case in public_cases]
        if principal.role != "guest":
            case_ids.extend(sorted(persisted_case_ids))
        return [
            repository.get_case(case_id)
            .to_public(replay_available=case_id in replay_cache)
            .model_dump(mode="json")
            for case_id in case_ids
        ]

    @app.get("/api/v1/incidents/{case_id}")
    def get_incident(
        case_id: str,
        principal: Principal = Depends(catalog_reader),
    ) -> dict[str, object]:
        allowed_case_ids = public_case_ids
        if principal.role != "guest":
            allowed_case_ids = public_case_ids | persisted_case_ids
        if case_id not in allowed_case_ids:
            raise HTTPException(status_code=404, detail="Incident case not found")
        try:
            case = repository.get_case(case_id)
            return case.to_public(
                replay_available=case.id in replay_cache
            ).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/incidents/import", status_code=status.HTTP_201_CREATED)
    async def import_incident(
        principal: Principal = Depends(admin), file: UploadFile = File(...)
    ) -> dict[str, object]:
        filename = file.filename or ""
        if "/" in filename or "\\" in filename or filename in {".", ".."}:
            raise HTTPException(status_code=400, detail="Incident filename must not contain a path")
        if file.content_type != "application/json" or not filename.lower().endswith(".json"):
            raise HTTPException(status_code=415, detail="Only JSON incident packs are accepted")
        content = await file.read(50 * 1024 * 1024 + 1)
        if len(content) > 50 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Incident pack exceeds 50 MB")
        try:
            case = IncidentCase.model_validate_json(content)
            package_hash = sha256(content).hexdigest()
            store.save_incident(case, package_hash)
            repository.add_case(case)
            persisted_case_ids.add(case.id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        store.record_audit(
            actor=principal.actor,
            action="incident.imported",
            resource_id=case.id,
            detail={"package_hash": package_hash, "size_bytes": len(content)},
        )
        return case.to_public().model_dump(mode="json")

    @app.post("/api/v1/investigations", status_code=status.HTTP_202_ACCEPTED)
    def create_investigation(
        payload: InvestigationCreate,
        principal: Principal = Depends(runner),
        idempotency_key: Annotated[
            str | None, Header(alias="Idempotency-Key", max_length=128)
        ] = None,
    ) -> dict[str, object]:
        try:
            case = repository.get_case(payload.incident_case_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        window_start = payload.start_at or case.starts_at
        window_end = payload.end_at or case.ends_at
        if window_start >= window_end:
            raise HTTPException(
                status_code=422,
                detail="Investigation start_at must be earlier than end_at",
            )
        case = case.model_copy(
            update={
                "starts_at": window_start,
                "ends_at": window_end,
                "evidence": [
                    item
                    for item in case.evidence
                    if item.timestamp is None
                    or window_start <= item.timestamp <= window_end
                ],
            }
        )
        request_fingerprint = sha256(
            json.dumps(
                {
                    "incident_case_id": case.id,
                    "mode": payload.mode,
                    "start_at": window_start.isoformat(),
                    "end_at": window_end.isoformat(),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        try:
            record, created = store.create_idempotent(
                case.id,
                payload.mode,
                owner_actor=principal.actor,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if not created:
            return {
                "investigation_id": record.id,
                "status": record.status,
                "mode": record.mode,
                "idempotent_replay": True,
            }

        store.record_audit(
            actor=principal.actor,
            action="investigation.created",
            resource_id=record.id,
            detail={"case_id": case.id, "mode": payload.mode},
        )

        if payload.mode == "live" and principal.role != "admin":
            if principal.token_hash is None:
                raise HTTPException(status_code=403, detail="Insufficient role")
            if not store.consume_daily_quota(
                principal.token_hash,
                datetime.now(UTC).date(),
                limit=settings.runner_daily_limit,
            ):
                store.mark_status(record.id, "canceled")
                raise HTTPException(
                    status_code=429,
                    detail="Daily live-run quota exhausted",
                )

        if settings.task_mode == "inline" or payload.mode == "replay":
            result = engine.run(
                case,
                investigation_id=record.id,
                on_event=lambda event: store.append_event(record.id, event),
            )
            store.save_result(record.id, result)
            telemetry.record_report(
                prompt_tokens=result.report.model_usage.prompt_tokens,
                completion_tokens=result.report.model_usage.completion_tokens,
                cost_cny=result.report.total_cost_cny,
                tool_calls=result.report.model_usage.tool_calls,
                latency_ms=result.report.total_latency_ms,
            )
        else:
            from incidentlens.tasks import run_investigation

            run_investigation.delay(
                record.id,
                case.model_dump_json(),
                settings.database_url,
            )
        return {
            "investigation_id": record.id,
            "status": "queued",
            "mode": payload.mode,
            "idempotent_replay": False,
        }

    @app.get("/api/v1/investigations")
    def list_investigations(
        principal: Principal = Depends(runner),
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
        status_filter: Annotated[str | None, Query(alias="status", max_length=30)] = None,
        case_id: Annotated[str | None, Query(max_length=120)] = None,
    ) -> dict[str, object]:
        return store.list_investigations(
            limit=limit,
            offset=offset,
            status=status_filter,
            case_id=case_id,
            owner_actor=None if principal.role == "admin" else principal.actor,
        )

    @app.get("/api/v1/audit-events")
    def list_audit_events(
        _principal: Principal = Depends(admin),
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
        action: Annotated[str | None, Query(max_length=100)] = None,
        resource_id: Annotated[str | None, Query(max_length=120)] = None,
    ) -> dict[str, object]:
        return store.list_audit_events(
            limit=limit,
            offset=offset,
            action=action,
            resource_id=resource_id,
        )

    @app.get("/api/v1/investigations/{investigation_id}")
    def get_investigation(
        investigation_id: str,
        principal: Principal = Depends(runner),
    ) -> dict[str, object]:
        return visible_investigation(investigation_id, principal)

    @app.post(
        "/api/v1/investigations/{investigation_id}/stream-ticket",
        response_model=StreamTicket,
        status_code=status.HTTP_201_CREATED,
    )
    def issue_stream_ticket(
        investigation_id: str,
        principal: Principal = Depends(runner),
    ) -> StreamTicket:
        visible_investigation(investigation_id, principal)
        expires_at = datetime.now(UTC) + timedelta(minutes=5)
        try:
            ticket = store.issue_stream_ticket(
                investigation_id,
                expires_at=expires_at,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail="Investigation not found",
            ) from exc
        store.record_audit(
            actor=principal.actor,
            action="investigation.stream_ticket_issued",
            resource_id=investigation_id,
            detail={"expires_at": expires_at.isoformat()},
        )
        return StreamTicket(ticket=ticket, expires_at=expires_at)

    @app.get("/api/v1/investigations/{investigation_id}/events")
    def investigation_events(
        request: Request,
        investigation_id: str,
        ticket: Annotated[str | None, Query(max_length=128)] = None,
    ) -> EventSourceResponse:
        if ticket is None or not store.validate_stream_ticket(investigation_id, ticket):
            raise HTTPException(status_code=403, detail="Invalid or expired stream ticket")
        if store.get(investigation_id) is None:
            raise HTTPException(status_code=404, detail="Investigation not found")
        header = request.headers.get("last-event-id", "0")
        try:
            after = max(int(header), 0)
        except ValueError:
            after = 0

        async def stream() -> AsyncIterator[dict[str, str]]:
            cursor = after
            terminal = {"completed", "failed", "canceled", "inconclusive"}
            while True:
                if await request.is_disconnected():
                    return
                current = store.get(investigation_id)
                if current is None:
                    return
                events = store.events_after(investigation_id, cursor)
                for event in events:
                    cursor = int(event["sequence"])
                    yield {
                        "id": str(cursor),
                        "event": str(event["type"]),
                        "data": json.dumps(event, ensure_ascii=False),
                    }
                if current["status"] in terminal and not events:
                    return
                await asyncio.sleep(0.2)

        return EventSourceResponse(stream(), ping=15)

    @app.post("/api/v1/investigations/{investigation_id}/cancel", status_code=202)
    def cancel_investigation(
        investigation_id: str, principal: Principal = Depends(runner)
    ) -> dict[str, str]:
        visible_investigation(investigation_id, principal)
        if not store.cancel(
            investigation_id,
            owner_actor=None if principal.role == "admin" else principal.actor,
        ):
            raise HTTPException(status_code=409, detail="Investigation cannot be canceled")
        store.record_audit(
            actor=principal.actor,
            action="investigation.canceled",
            resource_id=investigation_id,
        )
        return {"status": "canceled"}

    @app.post(
        "/api/v1/investigations/{investigation_id}/remediations/{proposal_id}/approve"
    )
    def approve_remediation(
        investigation_id: str,
        proposal_id: str,
        principal: Principal = Depends(admin),
    ) -> dict[str, object]:
        try:
            return store.approve_and_simulate(
                investigation_id,
                proposal_id,
                actor=principal.actor,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Remediation not found") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/v1/eval-runs")
    def create_eval_run(principal: Principal = Depends(admin)) -> dict[str, object]:
        result = EvaluationRunner(repository).run(include_hidden=True)
        store.record_audit(
            actor=principal.actor,
            action="evaluation.completed",
            resource_id=f"eval-{datetime.now(UTC).isoformat()}",
            detail={"case_count": result.case_count, "root_cause_top1": result.root_cause_top1},
        )
        return result.model_dump()

    @app.get("/api/v1/demo/replays/{case_id}")
    def replay(case_id: str) -> dict[str, object]:
        try:
            case = repository.get_case(case_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if case.visibility != "showcase":
            raise HTTPException(status_code=404, detail="Replay not found")
        cached = replay_cache.get(case.id)
        if cached is None:
            raise HTTPException(status_code=404, detail="Replay not found")
        return cached

    @app.get("/api/v1/openapi.json", include_in_schema=False)
    def openapi_alias(response: Response) -> dict[str, object]:
        response.headers["Cache-Control"] = "public, max-age=300"
        return app.openapi()

    return app


app = create_app()
