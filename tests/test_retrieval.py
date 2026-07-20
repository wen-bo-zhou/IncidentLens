from incidentlens.retrieval import EMBEDDING_DIMENSIONS, deterministic_embedding


def test_offline_embedding_is_stable_and_normalized() -> None:
    first = deterministic_embedding("connection pool exhaustion runbook")
    second = deterministic_embedding("connection pool exhaustion runbook")

    assert first == second
    assert len(first) == EMBEDDING_DIMENSIONS
    assert abs(sum(value * value for value in first) - 1.0) < 1e-6
