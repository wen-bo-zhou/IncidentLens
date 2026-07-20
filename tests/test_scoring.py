from incidentlens.scoring import confidence_for_score, score_hypothesis


def test_hypothesis_score_uses_locked_formula_and_contradiction_penalty() -> None:
    score = score_hypothesis(
        evidence_coverage=1.0,
        timeline_consistency=0.8,
        cross_signal_support=0.5,
        model_relevance=0.6,
        contradiction_penalty=0.1,
    )

    assert score == 0.69


def test_confidence_thresholds_are_stable() -> None:
    assert confidence_for_score(0.75) == "high"
    assert confidence_for_score(0.50) == "medium"
    assert confidence_for_score(0.49) == "low"

