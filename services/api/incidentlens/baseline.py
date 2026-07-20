from pydantic import BaseModel

from incidentlens.schemas import IncidentCase


class BaselineResult(BaseModel):
    root_cause_category: str
    evidence_ids: list[str]


class OneShotBaseline:
    """A deliberately small, no-tool baseline for regression comparisons."""

    def run(self, case: IncidentCase) -> BaselineResult:
        visible = [item for item in case.evidence if item.kind == "log"]
        text = " ".join(item.excerpt.casefold() for item in visible)
        terms: tuple[str, ...]
        if "pool exhausted" in text or "connection pool exhausted" in text:
            category = "db_pool_exhaustion"
            terms = ("pool exhausted", "connection pool exhausted")
        elif "poison message" in text or "deserialization failed" in text:
            category = "poison_message"
            terms = ("poison message", "deserialization failed")
        elif "timeout_ms" in text or ("release" in text and "timeout" in text):
            category = "deployment_config"
            terms = ("timeout_ms", "release", "timeout")
        else:
            category = "unknown"
            terms = ()
        evidence_ids = [
            item.id
            for item in visible
            if any(term in item.excerpt.casefold() for term in terms)
        ][:2]
        return BaselineResult(root_cause_category=category, evidence_ids=evidence_ids)
