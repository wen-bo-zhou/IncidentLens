from typing import Literal


def score_hypothesis(
    *,
    evidence_coverage: float,
    timeline_consistency: float,
    cross_signal_support: float,
    model_relevance: float,
    contradiction_penalty: float,
) -> float:
    values = [
        evidence_coverage,
        timeline_consistency,
        cross_signal_support,
        model_relevance,
        contradiction_penalty,
    ]
    if any(value < 0 or value > 1 for value in values):
        raise ValueError("Scoring inputs must be between 0 and 1")
    score = (
        0.40 * evidence_coverage
        + 0.25 * timeline_consistency
        + 0.20 * cross_signal_support
        + 0.15 * model_relevance
        - contradiction_penalty
    )
    return round(min(max(score, 0.0), 1.0), 2)


def confidence_for_score(score: float) -> Literal["high", "medium", "low"]:
    if score >= 0.75:
        return "high"
    if score >= 0.50:
        return "medium"
    return "low"

