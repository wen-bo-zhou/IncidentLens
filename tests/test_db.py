from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from incidentlens.auth import Principal
from incidentlens.db import (
    InvestigationStore,
    InvestigationStreamTicketRecord,
    create_session_factory,
)
from incidentlens.schemas import WorkflowEvent
from sqlalchemy import select, text


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


def test_short_rate_limit_cleanup_does_not_reset_a_longer_active_window(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    now = datetime(2026, 7, 30, 9, 4, tzinfo=UTC)

    assert store.consume_auth_failure(
        "long-window-client",
        now=now,
        window_seconds=300,
        limit=1,
    )[0] is True
    assert store.consume_auth_failure(
        "short-window-client",
        now=now,
        window_seconds=10,
        limit=1,
    )[0] is True
    assert store.consume_auth_failure(
        "long-window-client",
        now=now + timedelta(seconds=1),
        window_seconds=300,
        limit=1,
    )[0] is False


def test_rate_limit_storage_has_a_hard_cardinality_cap(tmp_path: Path) -> None:
    store = _store(tmp_path)
    now = datetime(2026, 7, 30, 9, 0, tzinfo=UTC)

    assert store.consume_auth_failure(
        "first-client",
        now=now,
        window_seconds=300,
        limit=10,
        max_records=2,
    )[0] is True
    assert store.consume_auth_failure(
        "second-client",
        now=now,
        window_seconds=300,
        limit=10,
        max_records=2,
    )[0] is True
    assert store.consume_auth_failure(
        "rotating-third-client",
        now=now,
        window_seconds=300,
        limit=10,
        max_records=2,
    )[0] is False
    assert store.consume_auth_failure(
        "rotating-third-client",
        now=now + timedelta(minutes=5),
        window_seconds=300,
        limit=10,
        max_records=2,
    )[0] is True


def test_oidc_login_transaction_is_hashed_browser_bound_and_single_use(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    now = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    state = "state-secret-value"
    browser_token = "browser-binding-secret"

    store.create_oidc_login(
        state=state,
        browser_token=browser_token,
        client_hash=sha256(b"client-a").hexdigest(),
        code_verifier="pkce-verifier",
        nonce="oidc-nonce",
        return_to="/operations",
        now=now,
        expires_at=now + timedelta(minutes=10),
        max_outstanding=100,
        max_outstanding_per_client=10,
    )

    with store.session_factory() as session:
        row = session.execute(
            text(
                "SELECT state_hash, browser_hash "
                "FROM oidc_login_transactions"
            )
        ).one()
    assert row.state_hash == sha256(state.encode()).hexdigest()
    assert row.browser_hash == sha256(browser_token.encode()).hexdigest()
    assert state not in row
    assert browser_token not in row
    assert (
        store.consume_oidc_login(
            state=state,
            browser_token="different-browser",
            now=now,
        )
        is None
    )
    assert store.consume_oidc_login(
        state=state,
        browser_token=browser_token,
        now=now,
    ) == {
        "code_verifier": "pkce-verifier",
        "nonce": "oidc-nonce",
        "return_to": "/operations",
    }
    assert (
        store.consume_oidc_login(
            state=state,
            browser_token=browser_token,
            now=now,
        )
        is None
    )


def test_oidc_login_transactions_have_global_and_per_client_caps(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    now = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)

    def create(
        suffix: str,
        client_hash: str,
        *,
        at: datetime = now,
    ) -> bool:
        return store.create_oidc_login(
            state=f"state-{suffix}",
            browser_token=f"browser-{suffix}",
            client_hash=sha256(client_hash.encode()).hexdigest(),
            code_verifier=f"verifier-{suffix}",
            nonce=f"nonce-{suffix}",
            return_to="/",
            now=at,
            expires_at=at + timedelta(minutes=10),
            max_outstanding=2,
            max_outstanding_per_client=1,
        )

    assert create("a", "client-a") is True
    assert create("a-duplicate", "client-a") is False
    assert create("b", "client-b") is True
    assert create("c", "client-c") is False
    assert create("after-expiry", "client-a", at=now + timedelta(minutes=10)) is True


def test_oidc_login_transaction_has_exactly_one_concurrent_consumer(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    now = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    state = "concurrent-state"
    browser_token = "concurrent-browser"
    assert store.create_oidc_login(
        state=state,
        browser_token=browser_token,
        client_hash=sha256(b"concurrent-client").hexdigest(),
        code_verifier="concurrent-verifier",
        nonce="concurrent-nonce",
        return_to="/",
        now=now,
        expires_at=now + timedelta(minutes=10),
        max_outstanding=100,
        max_outstanding_per_client=10,
    )

    def consume(_attempt: int) -> dict[str, str] | None:
        return store.consume_oidc_login(
            state=state,
            browser_token=browser_token,
            now=now,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(consume, range(2)))

    assert sum(result is not None for result in results) == 1


def test_browser_session_is_opaque_and_resolves_the_principal(tmp_path: Path) -> None:
    store = _store(tmp_path)
    now = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    principal = Principal(
        role="admin",
        actor="oidc-stable-actor",
        token_hash="stable-identity-hash",
    )

    session_token = store.create_browser_session(
        principal,
        now=now,
        expires_at=now + timedelta(hours=1),
    )

    with store.session_factory() as session:
        row = session.execute(
            text(
                "SELECT session_hash, actor, role, identity_hash "
                "FROM browser_sessions"
            )
        ).one()
    assert row.session_hash == sha256(session_token.encode()).hexdigest()
    assert row.session_hash != session_token
    assert row.actor == "oidc-stable-actor"
    assert row.role == "admin"
    assert row.identity_hash == "stable-identity-hash"
    assert store.authenticate_browser_session(session_token, now=now) == principal


def test_browser_session_expires_and_can_be_revoked(tmp_path: Path) -> None:
    store = _store(tmp_path)
    now = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    principal = Principal(
        role="runner",
        actor="oidc-runner",
        token_hash="runner-identity-hash",
    )
    expired = store.create_browser_session(
        principal,
        now=now,
        expires_at=now + timedelta(minutes=5),
    )
    revoked = store.create_browser_session(
        principal,
        now=now,
        expires_at=now + timedelta(hours=1),
    )

    assert (
        store.authenticate_browser_session(
            expired,
            now=now + timedelta(minutes=5),
        )
        is None
    )
    assert store.revoke_browser_session(revoked) is True
    assert store.authenticate_browser_session(revoked, now=now) is None
    assert store.revoke_browser_session(revoked) is False


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
