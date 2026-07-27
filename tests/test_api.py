import json
import logging
from datetime import UTC, datetime
from threading import Thread
from time import sleep

from fastapi.testclient import TestClient
from incidentlens.app import create_app
from incidentlens.observability import redact_access_log_path
from incidentlens.scenarios import ScenarioRepository
from incidentlens.schemas import WorkflowEvent

RUNNER_HEADERS = {"Authorization": "Bearer runner-demo-token"}


def _stream_ticket(client: TestClient, investigation_id: str) -> str:
    response = client.post(
        f"/api/v1/investigations/{investigation_id}/stream-ticket",
        headers=RUNNER_HEADERS,
    )
    assert response.status_code == 201
    return str(response.json()["ticket"])


def test_guest_can_list_showcase_cases_but_not_hidden_truth() -> None:
    client = TestClient(create_app(testing=True))

    response = client.get("/api/v1/incidents")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 3
    assert all("ground_truth" not in item for item in payload)
    assert all(item["replay_available"] is True for item in payload)


def test_versioned_openapi_schema_is_available() -> None:
    client = TestClient(create_app(testing=True))

    response = client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "IncidentLens API"
    assert response.json()["info"]["version"] == "0.3.0"


def test_runner_can_create_and_read_inline_investigation() -> None:
    client = TestClient(create_app(testing=True))
    runner_headers = {"Authorization": "Bearer runner-demo-token"}

    created = client.post(
        "/api/v1/investigations",
        headers=runner_headers,
        json={"incident_case_id": "deploy-timeout-showcase", "mode": "live"},
    )

    assert created.status_code == 202
    investigation_id = created.json()["investigation_id"]
    forbidden = client.get(f"/api/v1/investigations/{investigation_id}")
    detail = client.get(
        f"/api/v1/investigations/{investigation_id}",
        headers=runner_headers,
    )
    assert forbidden.status_code == 403
    assert detail.status_code == 200
    assert detail.json()["status"] == "completed"
    assert detail.json()["report"]["ranked_hypotheses"][0]["root_cause_category"] == (
        "deployment_config"
    )


def test_investigation_time_window_limits_the_evidence_used() -> None:
    client = TestClient(create_app(testing=True))

    created = client.post(
        "/api/v1/investigations",
        headers={"Authorization": "Bearer runner-demo-token"},
        json={
            "incident_case_id": "deploy-timeout-showcase",
            "mode": "live",
            "start_at": "2026-01-10T09:06:30Z",
            "end_at": "2026-01-10T09:07:30Z",
        },
    )

    assert created.status_code == 202
    detail = client.get(
        f"/api/v1/investigations/{created.json()['investigation_id']}",
        headers=RUNNER_HEADERS,
    ).json()
    assert detail["status"] == "inconclusive"
    assert [item["id"] for item in detail["report"]["evidence_index"]] == [
        "deploy-timeout-showcase:noise"
    ]


def test_investigation_rejects_an_invalid_time_window() -> None:
    client = TestClient(create_app(testing=True))

    response = client.post(
        "/api/v1/investigations",
        headers={"Authorization": "Bearer runner-demo-token"},
        json={
            "incident_case_id": "deploy-timeout-showcase",
            "mode": "live",
            "start_at": "2026-01-10T09:10:00Z",
            "end_at": "2026-01-10T09:05:00Z",
        },
    )

    assert response.status_code == 422


def test_idempotency_key_returns_the_original_investigation() -> None:
    client = TestClient(create_app(testing=True))
    headers = {
        "Authorization": "Bearer runner-demo-token",
        "Idempotency-Key": "checkout-incident-20260720",
    }
    payload = {"incident_case_id": "deploy-timeout-showcase", "mode": "live"}

    first = client.post("/api/v1/investigations", headers=headers, json=payload)
    second = client.post("/api/v1/investigations", headers=headers, json=payload)

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["investigation_id"] == first.json()["investigation_id"]
    assert second.json()["idempotent_replay"] is True


def test_idempotency_key_rejects_a_different_time_window() -> None:
    client = TestClient(create_app(testing=True))
    headers = {
        "Authorization": "Bearer runner-demo-token",
        "Idempotency-Key": "windowed-incident-20260727",
    }

    first = client.post(
        "/api/v1/investigations",
        headers=headers,
        json={
            "incident_case_id": "deploy-timeout-showcase",
            "mode": "live",
            "start_at": "2026-01-10T09:00:00Z",
            "end_at": "2026-01-10T09:30:00Z",
        },
    )
    second = client.post(
        "/api/v1/investigations",
        headers=headers,
        json={
            "incident_case_id": "deploy-timeout-showcase",
            "mode": "live",
            "start_at": "2026-01-10T09:30:00Z",
            "end_at": "2026-01-10T10:00:00Z",
        },
    )

    assert first.status_code == 202
    assert second.status_code == 409
    assert "another request" in second.json()["detail"]


def test_guest_cannot_trigger_live_investigation() -> None:
    client = TestClient(create_app(testing=True))

    response = client.post(
        "/api/v1/investigations",
        json={"incident_case_id": "deploy-timeout-showcase", "mode": "live"},
    )

    assert response.status_code == 403


def test_runner_daily_live_run_quota_is_enforced() -> None:
    client = TestClient(create_app(testing=True))
    payload = {"incident_case_id": "deploy-timeout-showcase", "mode": "live"}
    headers = {"Authorization": "Bearer runner-demo-token"}

    accepted = [
        client.post("/api/v1/investigations", headers=headers, json=payload)
        for _ in range(10)
    ]
    exhausted = client.post("/api/v1/investigations", headers=headers, json=payload)

    assert all(response.status_code == 202 for response in accepted)
    assert exhausted.status_code == 429
    assert exhausted.json()["detail"] == "Daily live-run quota exhausted"


def test_only_runner_or_admin_can_cancel_an_active_investigation() -> None:
    client = TestClient(create_app(testing=True))
    record = client.app.state.store.create("cancel-api-case", "live")

    forbidden = client.post(f"/api/v1/investigations/{record.id}/cancel")
    canceled = client.post(
        f"/api/v1/investigations/{record.id}/cancel",
        headers={"Authorization": "Bearer runner-demo-token"},
    )

    assert forbidden.status_code == 403
    assert canceled.status_code == 202
    assert canceled.json()["status"] == "canceled"


def test_public_replay_is_precomputed_and_stable() -> None:
    client = TestClient(create_app(testing=True))

    first = client.get("/api/v1/demo/replays/deploy-timeout-showcase")
    second = client.get("/api/v1/demo/replays/deploy-timeout-showcase")

    assert first.status_code == 200
    assert second.json() == first.json()
    assert first.json()["model_usage"]["model_calls"] == 0


def test_health_endpoints_are_available() -> None:
    client = TestClient(create_app(testing=True))

    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").status_code == 200


def test_sse_replays_ordered_events_and_respects_last_event_id() -> None:
    client = TestClient(create_app(testing=True))
    created = client.post(
        "/api/v1/investigations",
        headers={"Authorization": "Bearer runner-demo-token"},
        json={"incident_case_id": "db-pool-showcase", "mode": "live"},
    )
    investigation_id = created.json()["investigation_id"]
    ticket = _stream_ticket(client, investigation_id)

    response = client.get(
        f"/api/v1/investigations/{investigation_id}/events",
        headers={"Last-Event-ID": "2"},
        params={"ticket": ticket},
    )

    assert response.status_code == 200
    assert "id: 3" in response.text
    assert "event: stage_started" in response.text
    assert "id: 1\n" not in response.text


def test_sse_waits_for_events_created_after_subscription() -> None:
    app = create_app(testing=True)
    client = TestClient(app)
    record = app.state.store.create("deploy-timeout-showcase", "live")
    ticket = _stream_ticket(client, record.id)

    def finish_later() -> None:
        sleep(0.05)
        app.state.store.append_event(
            record.id,
            WorkflowEvent(
                sequence=1,
                type="stage_started",
                stage="collecting",
                message="collecting",
                created_at=datetime.now(UTC),
            ),
        )
        app.state.store.mark_status(record.id, "completed")

    writer = Thread(target=finish_later)
    writer.start()
    response = client.get(
        f"/api/v1/investigations/{record.id}/events",
        params={"ticket": ticket},
    )
    writer.join()

    assert response.status_code == 200
    assert "event: stage_started" in response.text
    assert '"sequence": 1' in response.text


def test_sse_requires_an_investigation_scoped_stream_ticket() -> None:
    client = TestClient(create_app(testing=True))
    runner_headers = {"Authorization": "Bearer runner-demo-token"}
    first = client.post(
        "/api/v1/investigations",
        headers=runner_headers,
        json={"incident_case_id": "deploy-timeout-showcase", "mode": "live"},
    )
    second = client.post(
        "/api/v1/investigations",
        headers=runner_headers,
        json={"incident_case_id": "db-pool-showcase", "mode": "live"},
    )
    first_id = first.json()["investigation_id"]
    second_id = second.json()["investigation_id"]

    missing = client.get(f"/api/v1/investigations/{first_id}/events")
    invalid = client.get(
        f"/api/v1/investigations/{first_id}/events",
        params={"ticket": "invalid"},
    )
    forbidden_issue = client.post(
        f"/api/v1/investigations/{first_id}/stream-ticket"
    )
    issued = client.post(
        f"/api/v1/investigations/{first_id}/stream-ticket",
        headers=runner_headers,
    )

    assert missing.status_code == 403
    assert invalid.status_code == 403
    assert forbidden_issue.status_code == 403
    assert issued.status_code == 201
    assert issued.json()["ticket"]
    assert issued.json()["expires_at"]

    ticket = issued.json()["ticket"]
    wrong_investigation = client.get(
        f"/api/v1/investigations/{second_id}/events",
        params={"ticket": ticket},
    )
    allowed = client.get(
        f"/api/v1/investigations/{first_id}/events",
        params={"ticket": ticket},
    )

    assert wrong_investigation.status_code == 403
    assert allowed.status_code == 200
    assert "event: report_ready" in allowed.text

    audit = client.get(
        "/api/v1/audit-events",
        headers={"Authorization": "Bearer admin-demo-token"},
        params={
            "action": "investigation.stream_ticket_issued",
            "resource_id": first_id,
        },
    )
    assert audit.status_code == 200
    assert audit.json()["total"] == 1
    assert ticket not in json.dumps(audit.json())


def test_only_admin_can_run_evaluation() -> None:
    client = TestClient(create_app(testing=True))

    forbidden = client.post(
        "/api/v1/eval-runs",
        headers={"Authorization": "Bearer runner-demo-token"},
    )
    allowed = client.post(
        "/api/v1/eval-runs",
        headers={"Authorization": "Bearer admin-demo-token"},
    )

    assert forbidden.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["case_count"] == 15


def test_admin_can_approve_exactly_one_sandbox_remediation() -> None:
    client = TestClient(create_app(testing=True))
    created = client.post(
        "/api/v1/investigations",
        headers={"Authorization": "Bearer runner-demo-token"},
        json={"incident_case_id": "poison-message-showcase", "mode": "live"},
    )
    investigation_id = created.json()["investigation_id"]
    detail = client.get(
        f"/api/v1/investigations/{investigation_id}",
        headers=RUNNER_HEADERS,
    ).json()
    proposal_id = detail["remediation_proposals"][0]["id"]

    approved = client.post(
        f"/api/v1/investigations/{investigation_id}/remediations/{proposal_id}/approve",
        headers={"Authorization": "Bearer admin-demo-token"},
    )
    repeated = client.post(
        f"/api/v1/investigations/{investigation_id}/remediations/{proposal_id}/approve",
        headers={"Authorization": "Bearer admin-demo-token"},
    )

    assert approved.status_code == 200
    assert approved.json()["status"] == "simulated"
    assert repeated.status_code == 409


def test_admin_can_import_valid_incident_pack() -> None:
    client = TestClient(create_app(testing=True))
    source = ScenarioRepository.seeded().get_case("deploy-timeout-showcase")
    imported = source.model_copy(
        update={"id": "customer-imported-showcase", "title": "导入的客户事故"}
    )

    response = client.post(
        "/api/v1/incidents/import",
        headers={"Authorization": "Bearer admin-demo-token"},
        files={
            "file": (
                "incident.json",
                json.dumps(imported.model_dump(mode="json"), ensure_ascii=False).encode(),
                "application/json",
            )
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] == "customer-imported-showcase"
    assert response.json()["replay_available"] is False
    detail = client.get("/api/v1/incidents/customer-imported-showcase")
    assert detail.status_code == 200
    assert "ground_truth" not in detail.json()
    assert client.app.state.store.list_incidents()[0].id == "customer-imported-showcase"
    assert client.app.state.store.runbook_chunk_count("customer-imported-showcase") == 1
    assert client.app.state.store.audit_actions("customer-imported-showcase") == [
        "incident.imported"
    ]


def test_admin_can_import_and_investigate_an_unlabeled_incident_pack() -> None:
    client = TestClient(create_app(testing=True))
    source = ScenarioRepository.seeded().get_case("db-pool-showcase")
    payload = source.model_dump(mode="json")
    payload["id"] = "customer-unlabeled-incident"
    payload["title"] = "未标注的客户事故"
    payload.pop("ground_truth")

    imported = client.post(
        "/api/v1/incidents/import",
        headers={"Authorization": "Bearer admin-demo-token"},
        files={
            "file": (
                "customer-incident.json",
                json.dumps(payload, ensure_ascii=False).encode(),
                "application/json",
            )
        },
    )

    assert imported.status_code == 201
    created = client.post(
        "/api/v1/investigations",
        headers={"Authorization": "Bearer runner-demo-token"},
        json={"incident_case_id": payload["id"], "mode": "live"},
    )
    assert created.status_code == 202
    detail = client.get(
        f"/api/v1/investigations/{created.json()['investigation_id']}",
        headers=RUNNER_HEADERS,
    ).json()
    assert detail["status"] == "completed"
    assert detail["report"]["ranked_hypotheses"][0]["root_cause_category"] == (
        "db_pool_exhaustion"
    )

    evaluation = client.post(
        "/api/v1/eval-runs",
        headers={"Authorization": "Bearer admin-demo-token"},
    )
    assert evaluation.status_code == 200
    assert evaluation.json()["case_count"] == 15


def test_import_rejects_non_json_and_non_admin() -> None:
    client = TestClient(create_app(testing=True))

    non_admin = client.post(
        "/api/v1/incidents/import",
        headers={"Authorization": "Bearer runner-demo-token"},
        files={"file": ("incident.json", b"{}", "application/json")},
    )
    wrong_type = client.post(
        "/api/v1/incidents/import",
        headers={"Authorization": "Bearer admin-demo-token"},
        files={"file": ("incident.txt", b"hello", "text/plain")},
    )
    path_traversal = client.post(
        "/api/v1/incidents/import",
        headers={"Authorization": "Bearer admin-demo-token"},
        files={"file": ("../incident.json", b"{}", "application/json")},
    )

    assert non_admin.status_code == 403
    assert wrong_type.status_code == 415
    assert path_traversal.status_code == 400


def test_prometheus_metrics_do_not_capture_request_content() -> None:
    client = TestClient(create_app(testing=True))
    client.get("/health/live")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "incidentlens_http_requests_total" in response.text
    assert "incidentlens_model_tokens_total" in response.text
    assert "incidentlens_investigation_duration_seconds" in response.text
    assert "health/live" not in response.text


def test_sse_ticket_is_redacted_from_access_log_paths() -> None:
    value = redact_access_log_path(
        "/api/v1/investigations/inv-1/events?ticket=raw-secret&after=2"
    )

    assert value == (
        "/api/v1/investigations/inv-1/events?ticket=[REDACTED]&after=2"
    )
    create_app(testing=True)
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg='%s - "%s %s HTTP/%s" %d',
        args=(
            "127.0.0.1",
            "GET",
            "/api/v1/investigations/inv-1/events?ticket=raw-secret",
            "1.1",
            200,
        ),
        exc_info=None,
    )
    for log_filter in logging.getLogger("uvicorn.access").filters:
        log_filter.filter(record)

    assert "raw-secret" not in record.getMessage()


def test_runner_can_filter_paginated_investigation_history() -> None:
    client = TestClient(create_app(testing=True))
    headers = {"Authorization": "Bearer runner-demo-token"}
    first = client.post(
        "/api/v1/investigations",
        headers=headers,
        json={"incident_case_id": "deploy-timeout-showcase", "mode": "live"},
    )
    second = client.post(
        "/api/v1/investigations",
        headers=headers,
        json={"incident_case_id": "db-pool-showcase", "mode": "live"},
    )

    forbidden = client.get("/api/v1/investigations")
    response = client.get(
        "/api/v1/investigations",
        headers=headers,
        params={
            "case_id": "db-pool-showcase",
            "status": "completed",
            "limit": 1,
            "offset": 0,
        },
    )

    assert forbidden.status_code == 403
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["investigation_id"] == second.json()[
        "investigation_id"
    ]
    assert response.json()["items"][0]["incident_case_id"] == "db-pool-showcase"
    assert response.json()["items"][0]["status"] == "completed"
    assert first.json()["investigation_id"] != second.json()["investigation_id"]


def test_only_admin_can_read_filtered_audit_history() -> None:
    client = TestClient(create_app(testing=True))
    runner_headers = {"Authorization": "Bearer runner-demo-token"}
    admin_headers = {"Authorization": "Bearer admin-demo-token"}
    created = client.post(
        "/api/v1/investigations",
        headers=runner_headers,
        json={"incident_case_id": "poison-message-showcase", "mode": "live"},
    )

    forbidden = client.get("/api/v1/audit-events", headers=runner_headers)
    response = client.get(
        "/api/v1/audit-events",
        headers=admin_headers,
        params={
            "action": "investigation.created",
            "resource_id": created.json()["investigation_id"],
        },
    )

    assert forbidden.status_code == 403
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["actor"] == "runner"
    assert response.json()["items"][0]["detail"]["case_id"] == (
        "poison-message-showcase"
    )
