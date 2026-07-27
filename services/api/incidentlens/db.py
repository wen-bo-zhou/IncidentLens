from __future__ import annotations

from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from secrets import token_urlsafe
from typing import Any, cast
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    delete,
    func,
    select,
    update,
)
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)
from sqlalchemy.pool import StaticPool

from incidentlens.retrieval import EMBEDDING_DIMENSIONS, deterministic_embedding
from incidentlens.schemas import IncidentCase, WorkflowEvent, WorkflowResult


class Base(DeclarativeBase):
    pass


class InvestigationRecord(Base):
    __tablename__ = "investigations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(120), index=True)
    mode: Mapped[str] = mapped_column(String(20))
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True, index=True
    )
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    report: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    events: Mapped[list[EventRecord]] = relationship(
        back_populates="investigation",
        cascade="all, delete-orphan",
        order_by="EventRecord.sequence",
    )


class EventRecord(Base):
    __tablename__ = "investigation_events"
    __table_args__ = (
        UniqueConstraint("investigation_id", "sequence", name="uq_event_investigation_sequence"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(40))
    stage: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(String(300))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    investigation: Mapped[InvestigationRecord] = relationship(back_populates="events")


class InvestigationStreamTicketRecord(Base):
    __tablename__ = "investigation_stream_tickets"

    ticket_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RemediationRecord(Base):
    __tablename__ = "remediations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="proposed")
    approved_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditRecord(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str] = mapped_column(String(120), index=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DailyRunUsageRecord(Base):
    __tablename__ = "daily_run_usage"

    usage_date: Mapped[date] = mapped_column(Date, primary_key=True)
    actor_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IncidentPackageRecord(Base):
    __tablename__ = "incident_packages"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    visibility: Mapped[str] = mapped_column(String(20), index=True)
    package_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RunbookChunkRecord(Base):
    __tablename__ = "runbook_chunks"

    id: Mapped[str] = mapped_column(String(180), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incident_packages.id"), index=True
    )
    service: Mapped[str] = mapped_column(String(120), index=True)
    content: Mapped[str] = mapped_column(String(2000))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))


def create_session_factory(database_url: str, *, testing: bool = False) -> sessionmaker[Session]:
    if database_url.startswith("sqlite:///"):
        database_path = Path(database_url.removeprefix("sqlite:///"))
        database_path.parent.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine_options: dict[str, Any] = {"connect_args": connect_args}
    if testing:
        engine_options["poolclass"] = StaticPool
    engine = create_engine(database_url, **engine_options)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


class InvestigationStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def create(
        self,
        case_id: str,
        mode: str,
        *,
        idempotency_key: str | None = None,
        request_fingerprint: str | None = None,
    ) -> InvestigationRecord:
        record, _created = self.create_idempotent(
            case_id,
            mode,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )
        return record

    def save_incident(self, case: IncidentCase, package_hash: str) -> None:
        with self.session_factory() as session:
            if session.get(IncidentPackageRecord, case.id) is not None:
                raise ValueError(f"Incident case already exists: {case.id}")
            duplicate_hash = session.scalar(
                select(IncidentPackageRecord.id).where(
                    IncidentPackageRecord.package_hash == package_hash
                )
            )
            if duplicate_hash is not None:
                raise ValueError(f"Incident package hash already exists: {duplicate_hash}")
            session.add(
                IncidentPackageRecord(
                    id=case.id,
                    visibility=case.visibility,
                    package_hash=package_hash,
                    payload=case.model_dump(mode="json"),
                    created_at=datetime.now(UTC),
                )
            )
            session.add_all(
                RunbookChunkRecord(
                    id=item.id,
                    incident_id=case.id,
                    service=item.service,
                    content=item.excerpt,
                    content_hash=item.content_hash,
                    embedding=deterministic_embedding(item.excerpt),
                )
                for item in case.evidence
                if item.kind == "runbook"
            )
            session.commit()

    def list_incidents(self) -> list[IncidentCase]:
        with self.session_factory() as session:
            records = session.scalars(
                select(IncidentPackageRecord).order_by(IncidentPackageRecord.created_at)
            ).all()
            return [IncidentCase.model_validate(record.payload) for record in records]

    def runbook_chunk_count(self, incident_id: str) -> int:
        with self.session_factory() as session:
            return int(
                session.scalar(
                    select(func.count(RunbookChunkRecord.id)).where(
                        RunbookChunkRecord.incident_id == incident_id
                    )
                )
                or 0
            )

    def record_audit(
        self,
        *,
        actor: str,
        action: str,
        resource_id: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        with self.session_factory() as session:
            session.add(
                AuditRecord(
                    actor=actor,
                    action=action,
                    resource_id=resource_id,
                    detail=detail or {},
                    created_at=datetime.now(UTC),
                )
            )
            session.commit()

    def audit_actions(self, resource_id: str) -> list[str]:
        with self.session_factory() as session:
            return list(
                session.scalars(
                    select(AuditRecord.action)
                    .where(AuditRecord.resource_id == resource_id)
                    .order_by(AuditRecord.id)
                ).all()
            )

    def list_audit_events(
        self,
        *,
        limit: int,
        offset: int,
        action: str | None = None,
        resource_id: str | None = None,
    ) -> dict[str, Any]:
        filters = []
        if action is not None:
            filters.append(AuditRecord.action == action)
        if resource_id is not None:
            filters.append(AuditRecord.resource_id == resource_id)
        with self.session_factory() as session:
            total = int(
                session.scalar(
                    select(func.count(AuditRecord.id)).where(*filters)
                )
                or 0
            )
            records = session.scalars(
                select(AuditRecord)
                .where(*filters)
                .order_by(AuditRecord.id.desc())
                .offset(offset)
                .limit(limit)
            ).all()
            return {
                "items": [
                    {
                        "id": record.id,
                        "actor": record.actor,
                        "action": record.action,
                        "resource_id": record.resource_id,
                        "detail": record.detail,
                        "created_at": record.created_at.isoformat(),
                    }
                    for record in records
                ],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    def consume_daily_quota(
        self,
        actor_hash: str,
        usage_date: date,
        *,
        limit: int,
    ) -> bool:
        now = datetime.now(UTC)
        with self.session_factory() as session:
            if session.get(DailyRunUsageRecord, (usage_date, actor_hash)) is None:
                session.add(
                    DailyRunUsageRecord(
                        usage_date=usage_date,
                        actor_hash=actor_hash,
                        run_count=0,
                        updated_at=now,
                    )
                )
                try:
                    session.commit()
                except IntegrityError:
                    session.rollback()
        with self.session_factory() as session:
            result = cast(
                CursorResult[Any],
                session.execute(
                    update(DailyRunUsageRecord)
                    .where(
                        DailyRunUsageRecord.usage_date == usage_date,
                        DailyRunUsageRecord.actor_hash == actor_hash,
                        DailyRunUsageRecord.run_count < limit,
                    )
                    .values(
                        run_count=DailyRunUsageRecord.run_count + 1,
                        updated_at=now,
                    )
                ),
            )
            session.commit()
            return result.rowcount == 1

    def ping(self) -> None:
        with self.session_factory() as session:
            session.execute(select(1))

    def issue_stream_ticket(
        self,
        investigation_id: str,
        *,
        expires_at: datetime,
    ) -> str:
        if expires_at.utcoffset() is None:
            raise ValueError("Stream ticket expiry must include a timezone")
        now = datetime.now(UTC)
        ticket = token_urlsafe(32)
        ticket_hash = sha256(ticket.encode()).hexdigest()
        with self.session_factory() as session:
            if session.get(InvestigationRecord, investigation_id) is None:
                raise KeyError(investigation_id)
            session.execute(
                delete(InvestigationStreamTicketRecord).where(
                    InvestigationStreamTicketRecord.expires_at <= now
                )
            )
            session.add(
                InvestigationStreamTicketRecord(
                    ticket_hash=ticket_hash,
                    investigation_id=investigation_id,
                    expires_at=expires_at,
                    created_at=now,
                )
            )
            session.commit()
        return ticket

    def validate_stream_ticket(
        self,
        investigation_id: str,
        ticket: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        checked_at = now or datetime.now(UTC)
        if checked_at.utcoffset() is None:
            raise ValueError("Stream ticket validation time must include a timezone")
        ticket_hash = sha256(ticket.encode()).hexdigest()
        with self.session_factory() as session:
            record = session.get(InvestigationStreamTicketRecord, ticket_hash)
            if record is None or record.investigation_id != investigation_id:
                return False
            expires_at = record.expires_at
            if expires_at.utcoffset() is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            return expires_at > checked_at

    def create_idempotent(
        self,
        case_id: str,
        mode: str,
        *,
        idempotency_key: str | None,
        request_fingerprint: str | None = None,
    ) -> tuple[InvestigationRecord, bool]:
        now = datetime.now(UTC)
        with self.session_factory() as session:
            if idempotency_key:
                existing = session.scalar(
                    select(InvestigationRecord).where(
                        InvestigationRecord.idempotency_key == idempotency_key
                    )
                )
                if existing is not None:
                    if self._idempotency_conflicts(
                        existing, case_id, mode, request_fingerprint
                    ):
                        raise ValueError("Idempotency key was already used for another request")
                    return existing, False
            record = InvestigationRecord(
                id=str(uuid4()),
                case_id=case_id,
                mode=mode,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
                status="queued",
                report=None,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                if not idempotency_key:
                    raise
                existing = session.scalar(
                    select(InvestigationRecord).where(
                        InvestigationRecord.idempotency_key == idempotency_key
                    )
                )
                if existing is None:
                    raise
                if self._idempotency_conflicts(
                    existing, case_id, mode, request_fingerprint
                ):
                    raise ValueError(
                        "Idempotency key was already used for another request"
                    ) from None
                return existing, False
            return record, True

    @staticmethod
    def _idempotency_conflicts(
        existing: InvestigationRecord,
        case_id: str,
        mode: str,
        request_fingerprint: str | None,
    ) -> bool:
        if existing.case_id != case_id or existing.mode != mode:
            return True
        return (
            existing.request_fingerprint is not None
            and existing.request_fingerprint != request_fingerprint
        )

    def append_event(self, investigation_id: str, event: WorkflowEvent) -> None:
        status_by_event = {
            "stage_started": event.stage,
            "run_failed": "failed",
            "run_canceled": "canceled",
        }
        with self.session_factory() as session:
            record = session.scalar(
                select(InvestigationRecord)
                .where(InvestigationRecord.id == investigation_id)
                .with_for_update()
            )
            if record is None:
                raise KeyError(investigation_id)
            if record.status == "canceled":
                return
            exists = session.scalar(
                select(EventRecord.id).where(
                    EventRecord.investigation_id == investigation_id,
                    EventRecord.sequence == event.sequence,
                )
            )
            if exists is None:
                session.add(
                    EventRecord(
                        investigation_id=investigation_id,
                        sequence=event.sequence,
                        type=event.type,
                        stage=event.stage,
                        message=event.message,
                        payload=event.payload,
                        created_at=event.created_at,
                    )
                )
            if event.type in status_by_event:
                record.status = status_by_event[event.type]
            record.updated_at = datetime.now(UTC)
            session.commit()

    def mark_status(self, investigation_id: str, status: str) -> None:
        with self.session_factory() as session:
            record = session.get(InvestigationRecord, investigation_id)
            if record is None:
                raise KeyError(investigation_id)
            record.status = status
            record.updated_at = datetime.now(UTC)
            session.commit()

    def is_canceled(self, investigation_id: str) -> bool:
        with self.session_factory() as session:
            record = session.get(InvestigationRecord, investigation_id)
            return bool(record and record.status == "canceled")

    def save_result(self, investigation_id: str, result: WorkflowResult) -> None:
        with self.session_factory() as session:
            record = session.scalar(
                select(InvestigationRecord)
                .where(InvestigationRecord.id == investigation_id)
                .with_for_update()
            )
            if record is None:
                raise KeyError(investigation_id)
            if record.status == "canceled":
                return
            record.status = result.status
            record.report = result.report.model_dump(mode="json")
            record.updated_at = datetime.now(UTC)
            existing_sequences = set(
                session.scalars(
                    select(EventRecord.sequence).where(
                        EventRecord.investigation_id == investigation_id
                    )
                ).all()
            )
            session.add_all(
                EventRecord(
                    investigation_id=investigation_id,
                    sequence=event.sequence,
                    type=event.type,
                    stage=event.stage,
                    message=event.message,
                    payload=event.payload,
                    created_at=event.created_at,
                )
                for event in result.events
                if event.sequence not in existing_sequences
            )
            existing_remediation = session.scalar(
                select(RemediationRecord.id)
                .where(RemediationRecord.investigation_id == investigation_id)
                .limit(1)
            )
            if existing_remediation is None:
                session.add_all(
                    RemediationRecord(
                        id=str(uuid4()),
                        investigation_id=investigation_id,
                        action_type=action.action_type,
                        title=action.title,
                        parameters={"risk": action.risk, "rationale": action.rationale},
                        status="proposed",
                        created_at=datetime.now(UTC),
                    )
                    for action in result.report.recommended_actions
                )
            session.commit()

    def get(self, investigation_id: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            record = session.get(InvestigationRecord, investigation_id)
            if record is None:
                return None
            remediations = session.scalars(
                select(RemediationRecord).where(
                    RemediationRecord.investigation_id == investigation_id
                )
            ).all()
            return {
                "investigation_id": record.id,
                "incident_case_id": record.case_id,
                "mode": record.mode,
                "status": record.status,
                "report": record.report,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
                "remediation_proposals": [
                    {
                        "id": item.id,
                        "action_type": item.action_type,
                        "title": item.title,
                        "status": item.status,
                        "parameters": item.parameters,
                    }
                    for item in remediations
                ],
            }

    def list_investigations(
        self,
        *,
        limit: int,
        offset: int,
        status: str | None = None,
        case_id: str | None = None,
    ) -> dict[str, Any]:
        filters = []
        if status is not None:
            filters.append(InvestigationRecord.status == status)
        if case_id is not None:
            filters.append(InvestigationRecord.case_id == case_id)
        with self.session_factory() as session:
            total = int(
                session.scalar(
                    select(func.count(InvestigationRecord.id)).where(*filters)
                )
                or 0
            )
            records = session.scalars(
                select(InvestigationRecord)
                .where(*filters)
                .order_by(
                    InvestigationRecord.created_at.desc(),
                    InvestigationRecord.id.desc(),
                )
                .offset(offset)
                .limit(limit)
            ).all()
            return {
                "items": [
                    {
                        "investigation_id": record.id,
                        "incident_case_id": record.case_id,
                        "mode": record.mode,
                        "status": record.status,
                        "summary": (
                            record.report.get("summary") if record.report else None
                        ),
                        "created_at": record.created_at.isoformat(),
                        "updated_at": record.updated_at.isoformat(),
                    }
                    for record in records
                ],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    def events_after(self, investigation_id: str, sequence: int) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            events = session.scalars(
                select(EventRecord)
                .where(
                    EventRecord.investigation_id == investigation_id,
                    EventRecord.sequence > sequence,
                )
                .order_by(EventRecord.sequence)
            ).all()
            return [
                {
                    "sequence": event.sequence,
                    "type": event.type,
                    "stage": event.stage,
                    "message": event.message,
                    "payload": event.payload,
                    "created_at": event.created_at.isoformat(),
                }
                for event in events
            ]

    def cancel(self, investigation_id: str) -> bool:
        with self.session_factory() as session:
            record = session.scalar(
                select(InvestigationRecord)
                .where(InvestigationRecord.id == investigation_id)
                .with_for_update()
            )
            active_statuses = {
                "queued",
                "collecting",
                "timeline_building",
                "hypothesizing",
                "verifying",
                "ranking",
                "reporting",
            }
            if record is None or record.status not in active_statuses:
                return False
            record.status = "canceled"
            record.updated_at = datetime.now(UTC)
            next_sequence = (
                session.scalar(
                    select(func.max(EventRecord.sequence)).where(
                        EventRecord.investigation_id == investigation_id
                    )
                )
                or 0
            ) + 1
            session.add(
                EventRecord(
                    investigation_id=investigation_id,
                    sequence=next_sequence,
                    type="run_canceled",
                    stage="canceled",
                    message="Investigation canceled by user",
                    payload={},
                    created_at=datetime.now(UTC),
                )
            )
            session.commit()
            return True

    def approve_and_simulate(
        self, investigation_id: str, proposal_id: str, *, actor: str
    ) -> dict[str, Any]:
        with self.session_factory() as session:
            proposal = session.get(RemediationRecord, proposal_id)
            if proposal is None or proposal.investigation_id != investigation_id:
                raise KeyError(proposal_id)
            if proposal.status != "proposed":
                raise RuntimeError("Remediation has already been handled")
            proposal.status = "simulated"
            proposal.approved_by = actor
            proposal.executed_at = datetime.now(UTC)
            session.add(
                AuditRecord(
                    actor=actor,
                    action="remediation.simulated",
                    resource_id=proposal_id,
                    detail={
                        "investigation_id": investigation_id,
                        "action_type": proposal.action_type,
                    },
                    created_at=datetime.now(UTC),
                )
            )
            session.commit()
            return {
                "proposal_id": proposal.id,
                "status": proposal.status,
                "simulated_change": {"action": proposal.action_type, **proposal.parameters},
            }
