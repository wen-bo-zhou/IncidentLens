from datetime import UTC, datetime
from pathlib import Path

import pytest
from incidentlens.db import InvestigationStore, create_session_factory
from incidentlens.schemas import WorkflowEvent


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
