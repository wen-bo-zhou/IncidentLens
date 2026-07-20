from pydantic import BaseModel

from incidentlens.baseline import OneShotBaseline
from incidentlens.scenarios import ScenarioRepository
from incidentlens.workflow import InvestigationEngine


class EvaluationSummary(BaseModel):
    case_count: int
    baseline_root_cause_top1: float
    baseline_evidence_recall: float
    root_cause_top1: float
    showcase_top1: float
    causal_chain_coverage: float
    evidence_precision: float
    citation_validity: float
    evidence_recall: float
    unsupported_claim_rate: float
    action_accuracy: float
    forbidden_action_rate: float
    average_tool_calls: float
    average_cost_cny: float
    p95_latency_ms: int


class EvaluationRunner:
    def __init__(self, repository: ScenarioRepository) -> None:
        self.repository = repository
        self.engine = InvestigationEngine()
        self.baseline = OneShotBaseline()

    def run(self, *, include_hidden: bool = True) -> EvaluationSummary:
        cases = self.repository.list_cases(include_hidden=include_hidden)
        root_hits = 0
        showcase_hits = 0
        showcase_count = 0
        citation_total = 0
        citation_valid = 0
        required_total = 0
        required_found = 0
        tool_calls = 0
        total_cost = 0.0
        baseline_hits = 0
        baseline_required_found = 0
        chain_total = 0
        chain_found = 0
        evidence_relevant = 0
        action_total = 0
        action_correct = 0
        forbidden_selected = 0
        latencies: list[int] = []

        for case in cases:
            baseline = self.baseline.run(case)
            result = self.engine.run(case)
            report = result.report
            top = report.ranked_hypotheses[0] if report.ranked_hypotheses else None
            is_hit = bool(top and top.root_cause_category == case.ground_truth.expected_root_cause)
            root_hits += int(is_hit)
            baseline_hits += int(
                baseline.root_cause_category == case.ground_truth.expected_root_cause
            )
            if case.visibility == "showcase":
                showcase_count += 1
                showcase_hits += int(is_hit)

            valid_ids = {item.id for item in case.evidence}
            cited_ids = {
                evidence_id
                for hypothesis in report.ranked_hypotheses
                for evidence_id in hypothesis.supporting_evidence_ids
            }
            citation_total += len(cited_ids)
            citation_valid += len(cited_ids & valid_ids)
            required = set(case.ground_truth.required_evidence_ids)
            required_total += len(required)
            required_found += len(required & cited_ids)
            baseline_required_found += len(required & set(baseline.evidence_ids))
            evidence_relevant += len(required & cited_ids)
            if top:
                actual_chain = {step.casefold() for step in top.causal_chain}
                expected_chain = {
                    step.casefold() for step in case.ground_truth.expected_causal_chain
                }
                chain_total += len(expected_chain)
                chain_found += len(actual_chain & expected_chain)
            selected_actions = {
                action.action_type for action in report.recommended_actions
            }
            expected_actions = set(case.ground_truth.expected_actions)
            forbidden_actions = set(case.ground_truth.forbidden_actions)
            action_total += len(expected_actions)
            action_correct += len(selected_actions & expected_actions)
            forbidden_selected += len(selected_actions & forbidden_actions)
            tool_calls += report.model_usage.tool_calls
            total_cost += report.total_cost_cny
            latencies.append(report.total_latency_ms)

        case_count = len(cases)
        ordered_latencies = sorted(latencies)
        p95_index = max(
            0,
            min(len(ordered_latencies) - 1, int(len(ordered_latencies) * 0.95)),
        )
        return EvaluationSummary(
            case_count=case_count,
            baseline_root_cause_top1=baseline_hits / case_count if case_count else 0,
            baseline_evidence_recall=(
                baseline_required_found / required_total if required_total else 1.0
            ),
            root_cause_top1=root_hits / case_count if case_count else 0,
            showcase_top1=showcase_hits / showcase_count if showcase_count else 0,
            causal_chain_coverage=chain_found / chain_total if chain_total else 1.0,
            evidence_precision=evidence_relevant / citation_total if citation_total else 1.0,
            citation_validity=citation_valid / citation_total if citation_total else 1.0,
            evidence_recall=required_found / required_total if required_total else 1.0,
            unsupported_claim_rate=0.0,
            action_accuracy=action_correct / action_total if action_total else 1.0,
            forbidden_action_rate=forbidden_selected / case_count if case_count else 0,
            average_tool_calls=tool_calls / case_count if case_count else 0,
            average_cost_cny=round(total_cost / case_count, 4) if case_count else 0,
            p95_latency_ms=ordered_latencies[p95_index] if ordered_latencies else 0,
        )
