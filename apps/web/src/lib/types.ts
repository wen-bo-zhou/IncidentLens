export type EvidenceKind = "log" | "metric" | "trace" | "runbook";

export interface IncidentCase {
  id: string;
  title: string;
  summary: string;
  scenario_family: string;
  visibility: "showcase" | "hidden";
  starts_at: string;
  ends_at: string;
  services: string[];
  evidence_count: number;
  replay_available: boolean;
  severity: "SEV-1" | "SEV-2" | "SEV-3";
}

export interface EvidenceRef {
  id: string;
  kind: EvidenceKind;
  timestamp: string | null;
  service: string;
  source: string;
  locator: string;
  excerpt: string;
  content_hash: string;
  attributes: Record<string, unknown>;
}

export interface TimelineItem {
  timestamp: string;
  category: "deployment" | "alert" | "error" | "latency" | "resource" | "queue";
  description: string;
  evidence_ids: string[];
}

export interface Hypothesis {
  id: string;
  title: string;
  root_cause_category: string;
  causal_chain: string[];
  supporting_evidence_ids: string[];
  contradicting_evidence_ids: string[];
  missing_evidence: string[];
  score: number;
  confidence: "high" | "medium" | "low";
  status: "pending" | "supported" | "contradicted" | "inconclusive";
}

export interface RecommendedAction {
  action_type: string;
  title: string;
  rationale: string;
  risk: "low" | "medium" | "high";
  requires_approval: boolean;
}

export interface InvestigationReport {
  investigation_id: string;
  summary: string;
  timeline: TimelineItem[];
  ranked_hypotheses: Hypothesis[];
  confirmed_facts: string[];
  uncertainties: string[];
  recommended_actions: RecommendedAction[];
  evidence_index: EvidenceRef[];
  model_usage: {
    provider: string;
    model: string;
    prompt_tokens: number;
    completion_tokens: number;
    model_calls: number;
    tool_calls: number;
  };
  total_cost_cny: number;
  total_latency_ms: number;
}

export interface EvaluationSummary {
  case_count: number;
  baseline_root_cause_top1: number;
  baseline_evidence_recall: number;
  root_cause_top1: number;
  showcase_top1: number;
  causal_chain_coverage: number;
  evidence_precision: number;
  citation_validity: number;
  evidence_recall: number;
  unsupported_claim_rate: number;
  action_accuracy: number;
  forbidden_action_rate: number;
  average_tool_calls: number;
  average_cost_cny: number;
  p95_latency_ms: number;
}

export type WorkflowEventType =
  | "stage_started"
  | "stage_completed"
  | "tool_started"
  | "tool_completed"
  | "hypothesis_updated"
  | "usage_updated"
  | "report_ready"
  | "run_failed"
  | "run_canceled";

export interface WorkflowEvent {
  sequence: number;
  type: WorkflowEventType;
  stage: string;
  message: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface RemediationProposal {
  id: string;
  action_type: string;
  title: string;
  status: string;
  parameters: Record<string, unknown>;
}

export interface InvestigationDetail {
  investigation_id: string;
  incident_case_id: string;
  mode: "live" | "replay";
  status: string;
  report: InvestigationReport | null;
  remediation_proposals: RemediationProposal[];
}

export interface StreamTicket {
  ticket: string;
  expires_at: string;
}

export interface InvestigationWindow {
  startAt: string;
  endAt: string;
}

export interface InvestigationSummary {
  investigation_id: string;
  incident_case_id: string;
  mode: "live" | "replay";
  status: string;
  summary: string | null;
  created_at: string;
  updated_at: string;
}

export interface AuditEvent {
  id: number;
  actor: string;
  action: string;
  resource_id: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
