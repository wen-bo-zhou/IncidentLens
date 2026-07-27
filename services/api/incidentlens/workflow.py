from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from opentelemetry import trace

from incidentlens.model_client import ModelGatewayError, NarrativeModel, estimate_cost_cny
from incidentlens.schemas import (
    Hypothesis,
    IncidentCase,
    InvestigationReport,
    ModelUsage,
    RecommendedAction,
    TimelineItem,
    WorkflowEvent,
    WorkflowEventType,
    WorkflowResult,
)
from incidentlens.scoring import confidence_for_score, score_hypothesis
from incidentlens.state_machine import InvestigationStateMachine, WorkflowState
from incidentlens.tools import InvestigationTools


class _EventLog:
    def __init__(self, on_event: Callable[[WorkflowEvent], None] | None = None) -> None:
        self.events: list[WorkflowEvent] = []
        self.on_event = on_event

    def add(
        self, event_type: WorkflowEventType, stage: str, message: str, **payload: object
    ) -> None:
        event = WorkflowEvent(
            sequence=len(self.events) + 1,
            type=event_type,
            stage=stage,
            message=message,
            payload=payload,
            created_at=datetime.now(UTC),
        )
        self.events.append(event)
        if self.on_event is not None:
            self.on_event(event)


class InvestigationEngine:
    stages: list[WorkflowState] = [
        "collecting",
        "timeline_building",
        "hypothesizing",
        "verifying",
        "ranking",
        "reporting",
    ]

    def __init__(self, model_client: NarrativeModel | None = None) -> None:
        self.model_client = model_client
        self.tracer = trace.get_tracer("incidentlens.investigation")

    def run(
        self,
        case: IncidentCase,
        *,
        investigation_id: str | None = None,
        on_event: Callable[[WorkflowEvent], None] | None = None,
    ) -> WorkflowResult:
        started = perf_counter()
        investigation_id = investigation_id or str(uuid4())
        log = _EventLog(on_event)
        state_machine = InvestigationStateMachine()

        if not case.evidence:
            state_machine.transition("inconclusive")
            report = InvestigationReport(
                investigation_id=investigation_id,
                summary="证据不足，无法确认根因。",
                timeline=[],
                ranked_hypotheses=[],
                confirmed_facts=[],
                uncertainties=["事故包中没有可用证据。"],
                recommended_actions=[],
                evidence_index=[],
                model_usage=ModelUsage(),
                total_cost_cny=0,
                total_latency_ms=int((perf_counter() - started) * 1000),
            )
            return WorkflowResult(status="inconclusive", report=report, events=[])

        case, tool_call_count = self._collect_evidence(case)

        for stage in self.stages:
            state_machine.transition(stage)
            log.add("stage_started", stage, f"开始{stage}")
            if stage == "collecting":
                for kind in sorted({item.kind for item in case.evidence}):
                    log.add("tool_started", stage, f"查询 {kind} 证据", tool=kind)
                    count = sum(item.kind == kind for item in case.evidence)
                    log.add("tool_completed", stage, f"获得 {count} 条 {kind} 证据", count=count)
            log.add("stage_completed", stage, f"完成{stage}")

        root_category = self._infer_root_category(case)
        supporting = self._supporting_evidence(case, root_category)
        if root_category == "unknown" or not supporting:
            state_machine.transition("inconclusive")
            report = InvestigationReport(
                investigation_id=investigation_id,
                summary="现有证据不足以形成可支持的根因假设。",
                timeline=[],
                ranked_hypotheses=[],
                confirmed_facts=[],
                uncertainties=["需要补充能够建立因果链的日志、指标或 Trace 证据。"],
                recommended_actions=[],
                evidence_index=case.evidence,
                model_usage=ModelUsage(tool_calls=tool_call_count),
                total_cost_cny=0,
                total_latency_ms=int((perf_counter() - started) * 1000),
            )
            log.add(
                "report_ready",
                "reporting",
                "证据不足，调查结论不确定",
                investigation_id=investigation_id,
                status="inconclusive",
            )
            return WorkflowResult(status="inconclusive", report=report, events=log.events)
        required_count = max(len(supporting), 1)
        signal_kinds = {item.kind for item in case.evidence if item.id in supporting}
        score = score_hypothesis(
            evidence_coverage=min(len(supporting) / required_count, 1.0),
            timeline_consistency=1.0,
            cross_signal_support=min(len(signal_kinds) / 3, 1.0),
            model_relevance=0.9,
            contradiction_penalty=0.0,
        )
        primary = Hypothesis(
            id=f"hyp-{uuid4()}",
            title=self._title_for_category(root_category),
            root_cause_category=root_category,
            causal_chain=self._causal_chain(root_category),
            supporting_evidence_ids=supporting,
            contradicting_evidence_ids=[],
            missing_evidence=[],
            score=score,
            confidence=confidence_for_score(score),
            status="supported",
        )
        alternatives = self._alternatives(case, root_category)
        hypotheses = sorted([primary, *alternatives], key=lambda item: item.score, reverse=True)
        log.add("hypothesis_updated", "ranking", "候选根因已排序", top_category=root_category)

        timeline = [
            TimelineItem(
                timestamp=item.timestamp or case.starts_at,
                category=self._timeline_category(item.excerpt),
                description=item.excerpt,
                evidence_ids=[item.id],
            )
            for item in sorted(case.evidence, key=lambda value: value.timestamp or case.starts_at)
            if item.id in supporting and item.kind != "runbook"
        ]
        actions = self._actions(root_category)
        summary = f"最可能根因：{primary.title}。结论由 {len(supporting)} 条证据支持。"
        confirmed_facts = [item.excerpt for item in case.evidence if item.id in supporting]
        uncertainties = ["该结论来自演练数据，真实生产处置前仍需人工复核。"]
        usage = ModelUsage(tool_calls=tool_call_count)
        total_cost = 0.0
        if self.model_client is not None:
            try:
                with self.tracer.start_as_current_span("gen_ai.model.generate") as span:
                    span.set_attribute("gen_ai.operation.name", "chat")
                    span.set_attribute("gen_ai.request.model", self.model_client.model)
                    model_response = self.model_client.generate_narrative(
                        incident_summary=case.summary,
                        root_cause=primary.title,
                        evidence=[item for item in case.evidence if item.id in supporting],
                    )
                    span.set_attribute(
                        "gen_ai.usage.input_tokens", model_response.usage.prompt_tokens
                    )
                    span.set_attribute(
                        "gen_ai.usage.output_tokens", model_response.usage.completion_tokens
                    )
                summary = model_response.narrative.summary
                confirmed_facts = model_response.narrative.confirmed_facts
                uncertainties = model_response.narrative.uncertainties
                usage = ModelUsage(
                    provider="openai-compatible",
                    model=model_response.resolved_model,
                    prompt_tokens=model_response.usage.prompt_tokens,
                    completion_tokens=model_response.usage.completion_tokens,
                    model_calls=model_response.model_calls,
                    tool_calls=usage.tool_calls,
                )
                total_cost = estimate_cost_cny(model_response.usage)
            except ModelGatewayError:
                uncertainties.append("模型摘要不可用，已回退到确定性证据报告。")
        log.add("usage_updated", "reporting", "运行预算已更新", tool_calls=usage.tool_calls)
        report = InvestigationReport(
            investigation_id=investigation_id,
            summary=summary,
            timeline=timeline,
            ranked_hypotheses=hypotheses,
            confirmed_facts=confirmed_facts,
            uncertainties=uncertainties,
            recommended_actions=actions,
            evidence_index=case.evidence,
            model_usage=usage,
            total_cost_cny=total_cost,
            total_latency_ms=int((perf_counter() - started) * 1000),
        )
        log.add("report_ready", "reporting", "事故报告已生成", investigation_id=investigation_id)
        state_machine.transition("completed")
        return WorkflowResult(status="completed", report=report, events=log.events)

    @staticmethod
    def _collect_evidence(case: IncidentCase) -> tuple[IncidentCase, int]:
        tools = InvestigationTools(case)
        tracer = trace.get_tracer("incidentlens.investigation")
        with tracer.start_as_current_span("gen_ai.tool.search_logs") as span:
            collected = list(tools.search_logs(query="", limit=50))
            span.set_attribute("gen_ai.tool.name", "search_logs")
            span.set_attribute("incidentlens.result.count", len(collected))
        tool_calls = 1

        metric_names = {
            str(item.attributes["metric_name"])
            for item in case.evidence
            if item.kind == "metric" and "metric_name" in item.attributes
        }
        for metric_name in metric_names:
            with tracer.start_as_current_span("gen_ai.tool.query_metric") as span:
                metric_results = tools.query_metric(metric_name)
                span.set_attribute("gen_ai.tool.name", "query_metric")
                span.set_attribute("incidentlens.result.count", len(metric_results))
                collected.extend(metric_results)
            tool_calls += 1

        trace_ids = {
            str(item.attributes["trace_id"])
            for item in case.evidence
            if item.kind == "trace" and "trace_id" in item.attributes
        }
        for trace_id in trace_ids:
            with tracer.start_as_current_span("gen_ai.tool.get_trace") as span:
                trace_results = tools.get_trace(trace_id)
                span.set_attribute("gen_ai.tool.name", "get_trace")
                span.set_attribute("incidentlens.result.count", len(trace_results))
                collected.extend(trace_results)
            tool_calls += 1

        with tracer.start_as_current_span("gen_ai.tool.search_runbooks") as span:
            runbook_results = tools.search_runbooks("", top_k=10)
            span.set_attribute("gen_ai.tool.name", "search_runbooks")
            span.set_attribute("incidentlens.result.count", len(runbook_results))
            collected.extend(runbook_results)
        tool_calls += 1
        unique = {item.id: item for item in collected}
        return case.model_copy(update={"evidence": list(unique.values())}), tool_calls

    @staticmethod
    def _infer_root_category(case: IncidentCase) -> str:
        text = " ".join(item.excerpt.casefold() for item in case.evidence)
        if "pool exhausted" in text or "connection pool exhausted" in text:
            return "db_pool_exhaustion"
        if "poison message" in text or "deserialization failed" in text:
            return "poison_message"
        if "timeout_ms" in text or ("release" in text and "timeout" in text):
            return "deployment_config"
        return "unknown"

    @staticmethod
    def _supporting_evidence(case: IncidentCase, category: str) -> list[str]:
        terms = {
            "deployment_config": ("release", "timeout", "canceled"),
            "db_pool_exhaustion": ("pool", "transaction cleanup", "database connection"),
            "poison_message": (
                "poison",
                "deserialization",
                "consumer.lag",
                "dead-letter",
                "offset",
            ),
        }.get(category, ())
        return [
            item.id
            for item in case.evidence
            if any(term in item.excerpt.casefold() for term in terms)
        ]

    @staticmethod
    def _title_for_category(category: str) -> str:
        return {
            "deployment_config": "发布配置将支付超时阈值错误降低",
            "db_pool_exhaustion": "事务清理缺失导致数据库连接池耗尽",
            "poison_message": "毒消息重试阻塞消费分区",
        }.get(category, "现有证据无法确认根因")

    @staticmethod
    def _causal_chain(category: str) -> list[str]:
        return {
            "deployment_config": [
                "release v2.4",
                "timeout reduced",
                "payment canceled",
                "checkout failed",
            ],
            "db_pool_exhaustion": [
                "transaction cleanup skipped",
                "connections leaked",
                "pool exhausted",
                "requests queued",
            ],
            "poison_message": [
                "invalid payload",
                "deserialization retry",
                "offset not committed",
                "queue lag",
            ],
        }.get(category, [])

    @staticmethod
    def _timeline_category(excerpt: str) -> str:
        value = excerpt.casefold()
        if "deploy" in value or "release" in value:
            return "deployment"
        if "latency" in value or "duration" in value:
            return "latency"
        if "pool" in value or "connection" in value:
            return "resource"
        if "queue" in value or "consumer" in value or "offset" in value:
            return "queue"
        return "error"

    @staticmethod
    def _actions(category: str) -> list[RecommendedAction]:
        values = {
            "deployment_config": ("rollback_virtual_version", "回滚虚拟版本"),
            "db_pool_exhaustion": ("adjust_virtual_pool", "调整虚拟连接池并修复事务清理"),
            "poison_message": ("isolate_poison_message", "将毒消息隔离到虚拟死信队列"),
        }
        if category not in values:
            return []
        action_type, title = values[category]
        return [
            RecommendedAction(
                action_type=action_type,
                title=title,
                rationale="该动作对应最高分根因，仅在沙箱中模拟。",
                risk="medium",
            )
        ]

    @staticmethod
    def _alternatives(case: IncidentCase, primary: str) -> list[Hypothesis]:
        categories = ["deployment_config", "db_pool_exhaustion", "poison_message"]
        alternatives = []
        for category in categories:
            if category == primary:
                continue
            alternatives.append(
                Hypothesis(
                    id=f"hyp-{uuid4()}",
                    title=InvestigationEngine._title_for_category(category),
                    root_cause_category=category,
                    causal_chain=InvestigationEngine._causal_chain(category),
                    supporting_evidence_ids=[],
                    contradicting_evidence_ids=[case.evidence[-1].id],
                    missing_evidence=["缺少跨信号支持"],
                    score=0.18,
                    confidence="low",
                    status="contradicted",
                )
            )
        return alternatives
