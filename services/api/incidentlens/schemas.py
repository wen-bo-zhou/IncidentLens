from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EvidenceKind = Literal["log", "metric", "trace", "runbook"]
Visibility = Literal["showcase", "hidden"]
Confidence = Literal["high", "medium", "low"]
HypothesisStatus = Literal["pending", "supported", "contradicted", "inconclusive"]
WorkflowEventType = Literal[
    "stage_started",
    "stage_completed",
    "tool_started",
    "tool_completed",
    "hypothesis_updated",
    "usage_updated",
    "report_ready",
    "run_failed",
    "run_canceled",
]


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=180, pattern=r"^[A-Za-z0-9_.:-]+$")
    kind: EvidenceKind
    timestamp: datetime | None = None
    service: str = Field(min_length=1, max_length=120)
    source: str = Field(min_length=1, max_length=240)
    locator: str = Field(min_length=1, max_length=240)
    excerpt: str = Field(min_length=1, max_length=280)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    attributes: dict[str, Any] = Field(default_factory=dict)


class GroundTruth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_root_cause: str
    expected_causal_chain: list[str]
    required_evidence_ids: list[str]
    distractor_evidence_ids: list[str] = Field(default_factory=list)
    expected_actions: list[str]
    forbidden_actions: list[str]


class PublicIncidentCase(BaseModel):
    id: str
    title: str
    summary: str
    scenario_family: str
    visibility: Visibility
    starts_at: datetime
    ends_at: datetime
    services: list[str]
    evidence_count: int
    replay_available: bool = False
    severity: Literal["SEV-1", "SEV-2", "SEV-3"] = "SEV-2"


class IncidentCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.-]+$")
    title: str
    summary: str
    scenario_family: str
    visibility: Visibility
    starts_at: datetime
    ends_at: datetime
    services: list[str]
    evidence: list[EvidenceRef]
    ground_truth: GroundTruth | None = None
    severity: Literal["SEV-1", "SEV-2", "SEV-3"] = "SEV-2"

    @model_validator(mode="after")
    def validate_incident_contract(self) -> IncidentCase:
        if self.starts_at.utcoffset() is None or self.ends_at.utcoffset() is None:
            raise ValueError("Incident timestamps must include a timezone")
        if any(
            item.timestamp is not None and item.timestamp.utcoffset() is None
            for item in self.evidence
        ):
            raise ValueError("Evidence timestamps must include a timezone")
        if self.starts_at >= self.ends_at:
            raise ValueError("Incident starts_at must be earlier than ends_at")
        evidence_ids = [item.id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Evidence IDs must be unique")
        for item in self.evidence:
            expected_hash = sha256(item.excerpt.encode("utf-8")).hexdigest()
            if item.content_hash != expected_hash:
                raise ValueError(f"Evidence content hash mismatch: {item.id}")
            if item.timestamp and not self.starts_at <= item.timestamp <= self.ends_at:
                raise ValueError(f"Evidence timestamp is outside incident range: {item.id}")
        valid_ids = set(evidence_ids)
        if self.ground_truth is not None:
            referenced_ids = {
                *self.ground_truth.required_evidence_ids,
                *self.ground_truth.distractor_evidence_ids,
            }
            if unknown := referenced_ids - valid_ids:
                raise ValueError(
                    f"Ground truth references unknown evidence: {sorted(unknown)}"
                )
        return self

    def to_public(self, *, replay_available: bool = False) -> PublicIncidentCase:
        return PublicIncidentCase(
            id=self.id,
            title=self.title,
            summary=self.summary,
            scenario_family=self.scenario_family,
            visibility=self.visibility,
            starts_at=self.starts_at,
            ends_at=self.ends_at,
            services=self.services,
            evidence_count=len(self.evidence),
            replay_available=replay_available,
            severity=self.severity,
        )


class TimelineItem(BaseModel):
    timestamp: datetime
    category: Literal["deployment", "alert", "error", "latency", "resource", "queue"]
    description: str
    evidence_ids: list[str]


class Hypothesis(BaseModel):
    id: str
    title: str
    root_cause_category: str
    causal_chain: list[str]
    supporting_evidence_ids: list[str]
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    score: float
    confidence: Confidence
    status: HypothesisStatus


class RecommendedAction(BaseModel):
    action_type: str
    title: str
    rationale: str
    risk: Literal["low", "medium", "high"]
    requires_approval: bool = True


class ModelUsage(BaseModel):
    provider: str = "offline"
    model: str = "evidence-rules-v1"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model_calls: int = 0
    tool_calls: int = 0


class InvestigationReport(BaseModel):
    investigation_id: str
    summary: str
    timeline: list[TimelineItem]
    ranked_hypotheses: list[Hypothesis]
    confirmed_facts: list[str]
    uncertainties: list[str]
    recommended_actions: list[RecommendedAction]
    evidence_index: list[EvidenceRef]
    model_usage: ModelUsage
    total_cost_cny: float
    total_latency_ms: int


class WorkflowEvent(BaseModel):
    sequence: int
    type: WorkflowEventType
    stage: str
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class WorkflowResult(BaseModel):
    status: Literal["completed", "failed", "canceled", "inconclusive"]
    report: InvestigationReport
    events: list[WorkflowEvent]
