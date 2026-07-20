from datetime import datetime

from incidentlens.schemas import EvidenceRef, IncidentCase


class InvestigationTools:
    def __init__(self, case: IncidentCase) -> None:
        self.case = case

    @staticmethod
    def _cap(limit: int) -> int:
        return min(max(limit, 1), 50)

    def search_logs(
        self,
        query: str,
        services: list[str] | None = None,
        levels: list[str] | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int = 50,
    ) -> list[EvidenceRef]:
        query_value = query.casefold().strip()
        service_set = set(services or [])
        level_set = {level.upper() for level in levels or []}
        results = []
        for item in self.case.evidence:
            if item.kind != "log":
                continue
            if query_value and query_value not in item.excerpt.casefold():
                continue
            if service_set and item.service not in service_set:
                continue
            if level_set and str(item.attributes.get("level", "")).upper() not in level_set:
                continue
            if start_at and item.timestamp and item.timestamp < start_at:
                continue
            if end_at and item.timestamp and item.timestamp > end_at:
                continue
            results.append(item)
        return results[: self._cap(limit)]

    def query_metric(
        self,
        metric_name: str,
        filters: dict[str, object] | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        step_seconds: int = 60,
    ) -> list[EvidenceRef]:
        del filters, step_seconds
        results = []
        for item in self.case.evidence:
            if item.kind != "metric":
                continue
            if metric_name and item.attributes.get("metric_name") != metric_name:
                continue
            if start_at and item.timestamp and item.timestamp < start_at:
                continue
            if end_at and item.timestamp and item.timestamp > end_at:
                continue
            results.append(item)
        return results[:50]

    def get_trace(self, trace_id: str) -> list[EvidenceRef]:
        return [
            item
            for item in self.case.evidence
            if item.kind == "trace"
            and (item.locator == trace_id or item.attributes.get("trace_id") == trace_id)
        ][:50]

    def search_runbooks(
        self, query: str, service: str | None = None, top_k: int = 5
    ) -> list[EvidenceRef]:
        tokens = {token for token in query.casefold().split() if len(token) > 2}
        candidates: list[tuple[int, EvidenceRef]] = []
        for item in self.case.evidence:
            if item.kind != "runbook" or (service and item.service != service):
                continue
            text = item.excerpt.casefold()
            score = sum(token in text for token in tokens)
            if not tokens or score:
                candidates.append((score, item))
        candidates.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in candidates[: min(max(top_k, 1), 10)]]

