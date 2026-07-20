from incidentlens.evals import EvaluationRunner
from incidentlens.scenarios import ScenarioRepository


def test_seeded_agent_meets_root_cause_and_citation_gates() -> None:
    result = EvaluationRunner(ScenarioRepository.seeded()).run(include_hidden=True)

    assert result.case_count == 15
    assert result.baseline_root_cause_top1 >= 0.80
    assert result.baseline_evidence_recall < result.evidence_recall
    assert result.root_cause_top1 >= 0.80
    assert result.showcase_top1 == 1.0
    assert result.causal_chain_coverage == 1.0
    assert result.citation_validity == 1.0
    assert result.evidence_recall >= 0.80
    assert result.action_accuracy == 1.0
    assert result.forbidden_action_rate == 0.0
