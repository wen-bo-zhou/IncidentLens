from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from incidentlens import tasks
from incidentlens.db import InvestigationStore, create_session_factory
from incidentlens.scenarios import ScenarioRepository
from incidentlens.schemas import WorkflowEvent


def _database_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def test_worker_persists_terminal_failure_when_engine_crashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = _database_url(tmp_path / "worker-failure.db")
    store = InvestigationStore(create_session_factory(database_url))
    case = ScenarioRepository.seeded().get_case("deploy-timeout-showcase")
    record = store.create(case.id, "live")

    class FailingEngine:
        def __init__(self, **_: object) -> None:
            pass

        def run(
            self,
            *_: object,
            on_event: Callable[[WorkflowEvent], None],
            **__: object,
        ) -> None:
            on_event(
                WorkflowEvent(
                    sequence=1,
                    type="stage_started",
                    stage="collecting",
                    message="collecting",
                    created_at=datetime.now(UTC),
                )
            )
            raise RuntimeError("simulated worker crash")

    monkeypatch.setattr(tasks, "InvestigationEngine", FailingEngine)

    with pytest.raises(RuntimeError, match="simulated worker crash"):
        tasks.run_investigation.run(record.id, case.model_dump_json(), database_url)

    detail = store.get(record.id)
    assert detail is not None
    assert detail["status"] == "failed"
    failure = store.events_after(record.id, 0)[-1]
    assert failure["sequence"] == 2
    assert failure["type"] == "run_failed"
    assert failure["stage"] == "failed"
    assert failure["payload"] == {"error_type": "RuntimeError"}


def test_worker_persists_completed_report_and_events(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path / "worker-success.db")
    store = InvestigationStore(create_session_factory(database_url))
    case = ScenarioRepository.seeded().get_case("db-pool-showcase")
    record = store.create(case.id, "live")

    tasks.run_investigation.run(record.id, case.model_dump_json(), database_url)

    detail = store.get(record.id)
    assert detail is not None
    assert detail["status"] == "completed"
    assert detail["report"]["ranked_hypotheses"][0]["root_cause_category"] == (
        "db_pool_exhaustion"
    )
    assert store.events_after(record.id, 0)[-1]["type"] == "report_ready"
    assert len(detail["remediation_proposals"]) == 1


def test_worker_does_not_restart_a_canceled_investigation(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path / "worker-canceled.db")
    store = InvestigationStore(create_session_factory(database_url))
    case = ScenarioRepository.seeded().get_case("poison-message-showcase")
    record = store.create(case.id, "live")
    assert store.cancel(record.id) is True

    tasks.run_investigation.run(record.id, case.model_dump_json(), database_url)

    detail = store.get(record.id)
    assert detail is not None
    assert detail["status"] == "canceled"
    assert detail["report"] is None
    assert [event["type"] for event in store.events_after(record.id, 0)] == [
        "run_canceled"
    ]
