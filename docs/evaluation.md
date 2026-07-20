# Evaluation contract

The seeded evaluation suite has three showcase cases and twelve hidden variants. `EvaluationRunner` runs both a no-tool one-shot baseline and the bounded Agent, then grades root-cause Top-1, causal-chain coverage, evidence precision/recall, citation validity, unsupported-claim rate, expected and forbidden actions, tool calls, cost and P95 latency.

Core correctness never depends on an LLM judge. Release gates are Top-1 ≥ 80%, showcase Top-1 = 100%, citation validity = 100%, evidence recall ≥ 80%, and unauthorized actions = 0. Run `pytest tests/test_evals.py -q` for the deterministic gate or `POST /api/v1/eval-runs` as an administrator for the API workflow.
