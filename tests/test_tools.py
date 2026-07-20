from datetime import UTC, datetime, timedelta

from incidentlens.scenarios import ScenarioRepository
from incidentlens.tools import InvestigationTools


def test_search_logs_filters_service_level_and_time() -> None:
    case = ScenarioRepository.seeded().get_case("deploy-timeout-showcase")
    tools = InvestigationTools(case)
    start = datetime(2026, 1, 10, 9, 0, tzinfo=UTC)

    results = tools.search_logs(
        query="timeout",
        services=["checkout-service"],
        levels=["ERROR"],
        start_at=start,
        end_at=start + timedelta(hours=1),
        limit=10,
    )

    assert results
    assert all(item.kind == "log" for item in results)
    assert all(item.service == "checkout-service" for item in results)
    assert all(len(item.excerpt) <= 280 for item in results)


def test_tool_result_limit_is_capped_at_fifty() -> None:
    case = ScenarioRepository.seeded().get_case("deploy-timeout-showcase")
    tools = InvestigationTools(case)

    results = tools.search_logs(query="", limit=500)

    assert len(results) <= 50


def test_metric_trace_and_runbook_tools_return_typed_evidence() -> None:
    case = ScenarioRepository.seeded().get_case("db-pool-showcase")
    tools = InvestigationTools(case)

    metrics = tools.query_metric("db.pool.active")
    trace = tools.get_trace("trace-db-pool-001")
    runbooks = tools.search_runbooks("connection pool", service="inventory-service", top_k=2)

    assert metrics and all(item.kind == "metric" for item in metrics)
    assert trace and all(item.kind == "trace" for item in trace)
    assert runbooks and all(item.kind == "runbook" for item in runbooks)

