from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from incidentlens.db import (
    InvestigationStore,
    InvestigationStreamTicketRecord,
    create_session_factory,
)
from incidentlens.schemas import WorkflowEvent
from sqlalchemy import select


def _store(tmp_path: Path) -> InvestigationStore:
    database_url = f"sqlite:///{(tmp_path / 'store.db').as_posix()}"
    return InvestigationStore(create_session_factory(database_url))


@pytest.mark.parametrize(
    "status",
    [
        "queued",
        "collecting",
        "timeline_building",
        "hypothesizing",
        "verifying",
        "ranking",
        "reporting",
    ],
)
def test_cancel_accepts_every_active_workflow_stage(tmp_path: Path, status: str) -> None:
    store = _store(tmp_path)
    record = store.create(f"case-{status}", "live")
    store.mark_status(record.id, status)

    assert store.cancel(record.id) is True
    assert store.get(record.id)["status"] == "canceled"  # type: ignore[index]
    assert store.events_after(record.id, 0)[0]["type"] == "run_canceled"


@pytest.mark.parametrize("status", ["completed", "failed", "canceled", "inconclusive"])
def test_cancel_rejects_terminal_workflow_statuses(tmp_path: Path, status: str) -> None:
    store = _store(tmp_path)
    record = store.create(f"case-{status}", "live")
    store.mark_status(record.id, status)

    assert store.cancel(record.id) is False


def test_late_worker_event_cannot_reopen_a_canceled_investigation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    record = store.create("case-cancel-race", "live")
    assert store.cancel(record.id) is True

    store.append_event(
        record.id,
        WorkflowEvent(
            sequence=2,
            type="stage_started",
            stage="collecting",
            message="late worker event",
            created_at=datetime.now(UTC),
        ),
    )

    assert store.get(record.id)["status"] == "canceled"  # type: ignore[index]
    assert [event["type"] for event in store.events_after(record.id, 0)] == [
        "run_canceled"
    ]


def test_investigation_history_is_newest_first_and_filterable(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = store.create("case-a", "live")
    store.mark_status(first.id, "completed")
    second = store.create("case-b", "replay")
    store.mark_status(second.id, "failed")
    third = store.create("case-a", "live")
    store.mark_status(third.id, "completed")

    page = store.list_investigations(
        limit=1,
        offset=0,
        status="completed",
        case_id="case-a",
    )

    assert page["total"] == 2
    assert [item["investigation_id"] for item in page["items"]] == [third.id]
    assert page["items"][0]["status"] == "completed"


def test_audit_history_is_newest_first_and_filterable(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.record_audit(
        actor="runner",
        action="investigation.created",
        resource_id="investigation-1",
    )
    store.record_audit(
        actor="admin",
        action="remediation.simulated",
        resource_id="proposal-1",
        detail={"investigation_id": "investigation-1"},
    )

    page = store.list_audit_events(
        limit=10,
        offset=0,
        action="remediation.simulated",
        resource_id=None,
    )

    assert page["total"] == 1
    assert page["items"] == [
        {
            "id": 2,
            "actor": "admin",
            "action": "remediation.simulated",
            "resource_id": "proposal-1",
            "detail": {"investigation_id": "investigation-1"},
            "created_at": page["items"][0]["created_at"],
        }
    ]


def test_daily_quota_is_durable_across_store_instances(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'quota.db').as_posix()}"
    first_store = InvestigationStore(create_session_factory(database_url))
    second_store = InvestigationStore(create_session_factory(database_url))
    today = date(2026, 7, 27)

    assert first_store.consume_daily_quota("runner-token-hash", today, limit=2) is True
    assert second_store.consume_daily_quota("runner-token-hash", today, limit=2) is True
    assert first_store.consume_daily_quota("runner-token-hash", today, limit=2) is False
    assert first_store.consume_daily_quota("different-runner", today, limit=2) is True


def test_auth_failure_limit_is_shared_across_store_instances_and_windows(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{(tmp_path / 'auth-failures.db').as_posix()}"
    first_store = InvestigationStore(create_session_factory(database_url))
    second_store = InvestigationStore(create_session_factory(database_url))
    now = datetime(2026, 7, 30, 9, 0, 30, tzinfo=UTC)

    assert first_store.consume_auth_failure(
        "client-hash",
        now=now,
        window_seconds=300,
        limit=2,
    ) == (True, 270)
    assert second_store.consume_auth_failure(
        "client-hash",
        now=now + timedelta(seconds=1),
        window_seconds=300,
        limit=2,
    ) == (True, 269)
    assert first_store.consume_auth_failure(
        "client-hash",
        now=now + timedelta(seconds=2),
        window_seconds=300,
        limit=2,
    ) == (False, 268)
    assert second_store.consume_auth_failure(
        "client-hash",
        now=now + timedelta(minutes=5),
        window_seconds=300,
        limit=2,
    ) == (True, 270)


def test_stream_ticket_is_scoped_hashed_and_expires(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = store.create("case-a", "live")
    second = store.create("case-b", "live")
    issued_at = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)

    ticket = store.issue_stream_ticket(
        first.id,
        expires_at=issued_at + timedelta(minutes=5),
    )

    assert store.validate_stream_ticket(first.id, ticket, now=issued_at) is True
    assert store.validate_stream_ticket(second.id, ticket, now=issued_at) is False
    assert (
        store.validate_stream_ticket(
            first.id,
            ticket,
            now=issued_at + timedelta(minutes=5),
        )
        is False
    )
    with store.session_factory() as session:
        stored_hash = session.scalar(
            select(InvestigationStreamTicketRecord.ticket_hash)
        )
    assert stored_hash is not None
    assert stored_hash != ticket
