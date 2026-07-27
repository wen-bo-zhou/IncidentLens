from hashlib import sha256

from incidentlens.model_client import ModelNarrative, ModelResponse, ModelUsageCost
from incidentlens.scenarios import ScenarioRepository
from incidentlens.workflow import InvestigationEngine


def test_engine_produces_evidence_backed_report_and_stage_events() -> None:
    case = ScenarioRepository.seeded().get_case("deploy-timeout-showcase")
    engine = InvestigationEngine()

    result = engine.run(case, investigation_id="inv-demo")

    assert result.report.ranked_hypotheses[0].root_cause_category == "deployment_config"
    assert result.report.ranked_hypotheses[0].supporting_evidence_ids
    assert result.report.timeline
    assert all(item.evidence_ids for item in result.report.timeline)
    evidence_by_id = {item.id: item for item in result.report.evidence_index}
    assert all(
        evidence_by_id[evidence_id].kind != "runbook"
        for timeline_item in result.report.timeline
        for evidence_id in timeline_item.evidence_ids
    )
    assert result.report.evidence_index
    assert result.report.total_cost_cny <= 0.20
    assert [event.type for event in result.events].count("stage_started") >= 6
    assert result.events[-1].type == "report_ready"


def test_engine_streams_every_event_to_callback_in_order() -> None:
    case = ScenarioRepository.seeded().get_case("db-pool-showcase")
    streamed = []

    result = InvestigationEngine().run(case, on_event=streamed.append)

    assert streamed == result.events
    assert [event.sequence for event in streamed] == list(range(1, len(streamed) + 1))


def test_engine_returns_inconclusive_when_evidence_is_insufficient() -> None:
    case = ScenarioRepository.seeded().get_case("deploy-timeout-showcase").model_copy(
        update={"evidence": []}
    )

    result = InvestigationEngine().run(case, investigation_id="inv-empty")

    assert result.status == "inconclusive"
    assert result.report.ranked_hypotheses == []


def test_engine_does_not_claim_a_root_cause_without_supporting_evidence() -> None:
    case = ScenarioRepository.seeded().get_case("deploy-timeout-showcase")
    excerpt = "Service returned an unfamiliar protocol error."
    evidence = case.evidence[0].model_copy(
        update={
            "excerpt": excerpt,
            "content_hash": sha256(excerpt.encode()).hexdigest(),
            "attributes": {},
        }
    )
    case = case.model_copy(update={"evidence": [evidence]})

    result = InvestigationEngine().run(case, investigation_id="inv-unknown")

    assert result.status == "inconclusive"
    assert result.report.ranked_hypotheses == []
    assert result.report.confirmed_facts == []
    assert result.report.recommended_actions == []
    assert result.report.evidence_index == [evidence]
    assert result.events[-1].type == "report_ready"
    assert result.events[-1].payload["status"] == "inconclusive"


def test_engine_uses_configured_model_for_auditable_narrative() -> None:
    class FakeModelClient:
        model = "fake-model-v1"

        def generate_narrative(self, **_: object) -> ModelResponse:
            return ModelResponse(
                narrative=ModelNarrative(
                    summary="模型生成的证据摘要",
                    confirmed_facts=["事实 A"],
                    uncertainties=["仍需人工确认"],
                ),
                usage=ModelUsageCost(prompt_tokens=100, completion_tokens=20),
                resolved_model="fake-model-v1",
            )

    case = ScenarioRepository.seeded().get_case("deploy-timeout-showcase")

    result = InvestigationEngine(model_client=FakeModelClient()).run(case)

    assert result.report.summary == "模型生成的证据摘要"
    assert result.report.model_usage.model == "fake-model-v1"
    assert result.report.model_usage.model_calls == 1
