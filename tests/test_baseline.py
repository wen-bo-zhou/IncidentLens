from incidentlens.baseline import OneShotBaseline
from incidentlens.scenarios import ScenarioRepository


def test_one_shot_baseline_has_no_tool_retrieval_and_cites_visible_logs() -> None:
    case = ScenarioRepository.seeded().get_case("deploy-timeout-showcase")

    result = OneShotBaseline().run(case)

    assert result.root_cause_category == "deployment_config"
    assert result.evidence_ids
    assert all(
        next(item for item in case.evidence if item.id == evidence_id).kind == "log"
        for evidence_id in result.evidence_ids
    )
