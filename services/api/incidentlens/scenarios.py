from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256

from incidentlens.schemas import EvidenceKind, EvidenceRef, GroundTruth, IncidentCase, Visibility


def _evidence(
    case_id: str,
    suffix: str,
    kind: EvidenceKind,
    timestamp: datetime,
    service: str,
    excerpt: str,
    *,
    locator: str | None = None,
    attributes: dict[str, object] | None = None,
) -> EvidenceRef:
    evidence_id = f"{case_id}:{suffix}"
    return EvidenceRef(
        id=evidence_id,
        kind=kind,
        timestamp=timestamp,
        service=service,
        source=f"seed/{case_id}",
        locator=locator or evidence_id,
        excerpt=excerpt[:280],
        content_hash=sha256(excerpt.encode("utf-8")).hexdigest(),
        attributes=attributes or {},
    )


def _build_case(family: str, visibility: Visibility, variant: int) -> IncidentCase:
    family_offsets = {"deployment_config": 0, "db_pool_exhaustion": 1, "poison_message": 2}
    offset = variant * 3 + family_offsets[family]
    base = datetime(2026, 1, 10, 9, 0, tzinfo=UTC) + timedelta(days=offset)
    suffix = "showcase" if visibility == "showcase" else f"hidden-{variant}"

    if family == "deployment_config":
        case_id = f"deploy-timeout-{suffix}"
        services = ["checkout-service", "payment-service", "gateway"]
        evidence = [
            _evidence(
                case_id,
                "deploy",
                "log",
                base + timedelta(minutes=4),
                "checkout-service",
                "release v2.4 deployed; PAYMENT_TIMEOUT_MS changed from 3000 to 120",
                attributes={"level": "INFO", "event": "deployment"},
            ),
            _evidence(
                case_id,
                "timeout",
                "log",
                base + timedelta(minutes=8),
                "checkout-service",
                "payment request timeout after 120ms; checkout aborted",
                attributes={"level": "ERROR", "trace_id": f"trace-deploy-{variant:03d}"},
            ),
            _evidence(
                case_id,
                "latency",
                "metric",
                base + timedelta(minutes=9),
                "payment-service",
                "payment latency p95 remained 420ms while checkout timeout errors spiked",
                attributes={
                    "metric_name": "http.server.duration.p95",
                    "value": 0.42,
                    "unit": "s",
                    "series": [0.38, 0.40, 0.41, 0.42, 0.43, 0.42],
                    "anomaly_index": 3,
                },
            ),
            _evidence(
                case_id,
                "trace",
                "trace",
                base + timedelta(minutes=8),
                "checkout-service",
                "checkout span canceled payment child span at 120ms before successful completion",
                locator=f"trace-deploy-{variant:03d}",
                attributes={
                    "trace_id": f"trace-deploy-{variant:03d}",
                    "duration_ms": 121,
                    "spans": [
                        {"name": "POST /checkout", "start_ms": 0, "duration_ms": 121},
                        {"name": "payment.authorize", "start_ms": 2, "duration_ms": 119},
                        {"name": "gateway.request", "start_ms": 8, "duration_ms": 113},
                    ],
                },
            ),
            _evidence(
                case_id,
                "runbook",
                "runbook",
                base,
                "checkout-service",
                "For post-deploy payment timeouts, compare PAYMENT_TIMEOUT_MS and roll back "
                "virtual version.",
                attributes={"title": "Checkout timeout runbook"},
            ),
            _evidence(
                case_id,
                "noise",
                "log",
                base + timedelta(minutes=7),
                "gateway",
                "certificate rotation completed successfully",
                attributes={"level": "INFO"},
            ),
        ]
        required = [f"{case_id}:deploy", f"{case_id}:timeout", f"{case_id}:trace"]
        truth = GroundTruth(
            expected_root_cause=family,
            expected_causal_chain=[
                "release v2.4",
                "timeout reduced",
                "payment canceled",
                "checkout failed",
            ],
            required_evidence_ids=required,
            distractor_evidence_ids=[f"{case_id}:noise"],
            expected_actions=["rollback_virtual_version"],
            forbidden_actions=["restart_database", "run_shell"],
        )
        title = "结算发布后支付超时"
        summary = "结算成功率在新版本发布后迅速下降。"
    elif family == "db_pool_exhaustion":
        case_id = f"db-pool-{suffix}"
        services = ["inventory-service", "postgres", "gateway"]
        trace_id = (
            "trace-db-pool-001"
            if visibility == "showcase"
            else f"trace-db-pool-{variant:03d}"
        )
        evidence = [
            _evidence(
                case_id,
                "pool-error",
                "log",
                base + timedelta(minutes=12),
                "inventory-service",
                "database connection pool exhausted; acquire timed out after 5000ms",
                attributes={"level": "ERROR", "trace_id": trace_id},
            ),
            _evidence(
                case_id,
                "pool-active",
                "metric",
                base + timedelta(minutes=10),
                "inventory-service",
                "db.pool.active reached 20 of 20 and db.pool.pending rose to 84",
                attributes={
                    "metric_name": "db.pool.active",
                    "value": 20,
                    "limit": 20,
                    "unit": "connections",
                    "series": [8, 11, 15, 18, 20, 20],
                    "anomaly_index": 4,
                },
            ),
            _evidence(
                case_id,
                "trace",
                "trace",
                base + timedelta(minutes=12),
                "inventory-service",
                "reserve-stock span spent 5.0s waiting for a database connection",
                locator=trace_id,
                attributes={
                    "trace_id": trace_id,
                    "duration_ms": 5032,
                    "spans": [
                        {"name": "POST /reserve", "start_ms": 0, "duration_ms": 5032},
                        {"name": "reserve-stock", "start_ms": 12, "duration_ms": 5012},
                        {"name": "db.pool.acquire", "start_ms": 18, "duration_ms": 5000},
                    ],
                },
            ),
            _evidence(
                case_id,
                "leak",
                "log",
                base + timedelta(minutes=5),
                "inventory-service",
                "transaction cleanup skipped on reservation validation failure",
                attributes={"level": "WARN", "event": "resource_leak"},
            ),
            _evidence(
                case_id,
                "runbook",
                "runbook",
                base,
                "inventory-service",
                "Connection pool exhaustion: inspect pending transactions, then adjust virtual "
                "pool only after approval.",
                attributes={"title": "Inventory connection pool"},
            ),
            _evidence(
                case_id,
                "noise",
                "metric",
                base + timedelta(minutes=11),
                "gateway",
                "gateway CPU stable at 31 percent",
                attributes={"metric_name": "process.cpu.utilization", "value": 0.31},
            ),
        ]
        required = [f"{case_id}:pool-error", f"{case_id}:pool-active", f"{case_id}:leak"]
        truth = GroundTruth(
            expected_root_cause=family,
            expected_causal_chain=[
                "transaction cleanup skipped",
                "connections leaked",
                "pool exhausted",
                "requests queued",
            ],
            required_evidence_ids=required,
            distractor_evidence_ids=[f"{case_id}:noise"],
            expected_actions=["adjust_virtual_pool"],
            forbidden_actions=["drop_database", "run_shell"],
        )
        title = "库存服务连接池耗尽"
        summary = "库存预留请求延迟上升并大量超时。"
    else:
        case_id = f"poison-message-{suffix}"
        services = ["order-consumer", "order-api", "queue"]
        trace_id = f"trace-poison-{variant:03d}"
        evidence = [
            _evidence(
                case_id,
                "decode",
                "log",
                base + timedelta(minutes=15),
                "order-consumer",
                "poison message deserialization failed at offset 8842; retrying same message",
                attributes={"level": "ERROR", "trace_id": trace_id},
            ),
            _evidence(
                case_id,
                "lag",
                "metric",
                base + timedelta(minutes=18),
                "queue",
                "consumer.lag increased from 3 to 14820 while publish rate remained normal",
                attributes={
                    "metric_name": "messaging.consumer.lag",
                    "value": 14820,
                    "unit": "messages",
                    "series": [3, 18, 240, 1900, 7210, 14820],
                    "anomaly_index": 2,
                },
            ),
            _evidence(
                case_id,
                "retry-trace",
                "trace",
                base + timedelta(minutes=16),
                "order-consumer",
                "consumer repeatedly processed offset 8842 and never committed the partition",
                locator=trace_id,
                attributes={
                    "trace_id": trace_id,
                    "offset": 8842,
                    "duration_ms": 900,
                    "spans": [
                        {"name": "consume offset 8842", "start_ms": 0, "duration_ms": 900},
                        {"name": "deserialize", "start_ms": 20, "duration_ms": 110},
                        {"name": "retry.backoff", "start_ms": 140, "duration_ms": 740},
                    ],
                },
            ),
            _evidence(
                case_id,
                "dlq-config",
                "log",
                base + timedelta(minutes=3),
                "order-consumer",
                "dead-letter routing disabled for schema errors",
                attributes={"level": "WARN", "event": "configuration"},
            ),
            _evidence(
                case_id,
                "runbook",
                "runbook",
                base,
                "order-consumer",
                "When one offset blocks a partition, isolate the poison message to the virtual "
                "DLQ after approval.",
                attributes={"title": "Queue poison message"},
            ),
            _evidence(
                case_id,
                "noise",
                "log",
                base + timedelta(minutes=17),
                "order-api",
                "daily analytics export completed",
                attributes={"level": "INFO"},
            ),
        ]
        required = [f"{case_id}:decode", f"{case_id}:lag", f"{case_id}:dlq-config"]
        truth = GroundTruth(
            expected_root_cause=family,
            expected_causal_chain=[
                "invalid payload",
                "deserialization retry",
                "offset not committed",
                "queue lag",
            ],
            required_evidence_ids=required,
            distractor_evidence_ids=[f"{case_id}:noise"],
            expected_actions=["isolate_poison_message"],
            forbidden_actions=["purge_queue", "run_shell"],
        )
        title = "毒消息阻塞订单消费"
        summary = "订单消息持续积压，消费者吞吐降至接近零。"

    return IncidentCase(
        id=case_id,
        title=title,
        summary=summary,
        scenario_family=family,
        visibility=visibility,
        starts_at=base,
        ends_at=base + timedelta(hours=1),
        services=services,
        evidence=evidence,
        ground_truth=truth,
    )


class ScenarioRepository:
    def __init__(self, cases: list[IncidentCase]) -> None:
        self._cases = {case.id: case for case in cases}

    @classmethod
    def seeded(cls) -> ScenarioRepository:
        families = ["deployment_config", "db_pool_exhaustion", "poison_message"]
        cases = [_build_case(family, "showcase", 0) for family in families]
        cases.extend(
            _build_case(family, "hidden", variant)
            for family in families
            for variant in range(1, 5)
        )
        return cls(cases)

    def list_cases(self, *, include_hidden: bool = False) -> list[IncidentCase]:
        cases = list(self._cases.values())
        if not include_hidden:
            cases = [case for case in cases if case.visibility == "showcase"]
        return cases

    def get_case(self, case_id: str) -> IncidentCase:
        try:
            return self._cases[case_id]
        except KeyError as exc:
            raise KeyError(f"Unknown incident case: {case_id}") from exc

    def add_case(self, case: IncidentCase) -> None:
        if case.id in self._cases:
            raise ValueError(f"Incident case already exists: {case.id}")
        self._cases[case.id] = case
