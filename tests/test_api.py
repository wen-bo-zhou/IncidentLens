import json
from datetime import UTC, datetime
from threading import Thread
from time import sleep

from fastapi.testclient import TestClient
from incidentlens.app import create_app
from incidentlens.scenarios import ScenarioRepository
from incidentlens.schemas import WorkflowEvent


def test_guest_can_list_showcase_cases_but_not_hidden_truth() -> None:
    client = TestClient(create_app(testing=True))

    response = client.get("/api/v1/incidents")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 3
    assert all("ground_truth" not in item for item in payload)


def test_runner_can_create_and_read_inline_investigation() -> None:
    client = TestClient(create_app(testing=True))

    created = client.post(
        "/api/v1/investigations",
        headers={"Authorization": "Bearer runner-demo-token"},
        json={"incident_case_id": "deploy-timeout-showcase", "mode": "live"},
    )

    assert created.status_code == 202
    investigation_id = created.json()["investigation_id"]
    detail = client.get(f"/api/v1/investigations/{investigation_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "completed"
    assert detail.json()["report"]["ranked_hypotheses"][0]["root_cause_category"] == (
        "deployment_config"
    )


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


def test_guest_cannot_trigger_live_investigation() -> None:
    client = TestClient(create_app(testing=True))

    response = client.post(
        "/api/v1/investigations",
        json={"incident_case_id": "deploy-timeout-showcase", "mode": "live"},
    )

    assert response.status_code == 403


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

    response = client.get(
        f"/api/v1/investigations/{investigation_id}/events",
        headers={"Last-Event-ID": "2"},
    )

    assert response.status_code == 200
    assert "id: 3" in response.text
    assert "event: stage_started" in response.text
    assert "id: 1\n" not in response.text


def test_sse_waits_for_events_created_after_subscription() -> None:
    app = create_app(testing=True)
    client = TestClient(app)
    record = app.state.store.create("deploy-timeout-showcase", "live")

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
    response = client.get(f"/api/v1/investigations/{record.id}/events")
    writer.join()

    assert response.status_code == 200
    assert "event: stage_started" in response.text
    assert '"sequence": 1' in response.text


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
    detail = client.get(f"/api/v1/investigations/{investigation_id}").json()
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
    detail = client.get("/api/v1/incidents/customer-imported-showcase")
    assert detail.status_code == 200
    assert "ground_truth" not in detail.json()
    assert client.app.state.store.list_incidents()[0].id == "customer-imported-showcase"
    assert client.app.state.store.runbook_chunk_count("customer-imported-showcase") == 1
    assert client.app.state.store.audit_actions("customer-imported-showcase") == [
        "incident.imported"
    ]


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
