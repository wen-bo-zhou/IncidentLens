import logging
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import perf_counter

from fastapi import FastAPI, Request, Response
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Tracer
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST

_tracer_provider: TracerProvider | None = None
_SENSITIVE_QUERY = re.compile(r"([?&]ticket=)[^&\s]*")


def redact_access_log_path(path: str) -> str:
    return _SENSITIVE_QUERY.sub(r"\1[REDACTED]", path)


class _SensitiveQueryFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        arguments = record.args
        if (
            record.name == "uvicorn.access"
            and isinstance(arguments, tuple)
            and len(arguments) >= 3
            and isinstance(arguments[2], str)
        ):
            record.args = (
                *arguments[:2],
                redact_access_log_path(arguments[2]),
                *arguments[3:],
            )
        return True


def _configure_access_log_redaction() -> None:
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, _SensitiveQueryFilter) for item in logger.filters):
        logger.addFilter(_SensitiveQueryFilter())


def configure_tracer(service_name: str) -> Tracer:
    global _tracer_provider
    if _tracer_provider is None:
        _tracer_provider = TracerProvider(
            resource=Resource.create({"service.name": service_name})
        )
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
        if otlp_endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            _tracer_provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True))
            )
        trace.set_tracer_provider(_tracer_provider)
    return trace.get_tracer(service_name)


@dataclass
class TelemetryMetrics:
    tokens: Counter
    model_cost: Counter
    tool_calls: Counter
    investigation_latency: Histogram

    def record_report(
        self,
        *,
        prompt_tokens: int,
        completion_tokens: int,
        cost_cny: float,
        tool_calls: int,
        latency_ms: int,
    ) -> None:
        self.tokens.labels(kind="prompt").inc(prompt_tokens)
        self.tokens.labels(kind="completion").inc(completion_tokens)
        self.model_cost.inc(cost_cny)
        self.tool_calls.inc(tool_calls)
        self.investigation_latency.observe(latency_ms / 1000)


def configure_observability(app: FastAPI) -> TelemetryMetrics:
    _configure_access_log_redaction()
    registry = CollectorRegistry()
    requests = Counter(
        "incidentlens_http_requests_total",
        "HTTP requests processed without recording request paths or content",
        ["method", "status"],
        registry=registry,
    )
    latency = Histogram(
        "incidentlens_http_request_duration_seconds",
        "HTTP request latency without request content",
        ["method"],
        registry=registry,
    )
    telemetry = TelemetryMetrics(
        tokens=Counter(
            "incidentlens_model_tokens_total",
            "Model tokens by non-sensitive token kind",
            ["kind"],
            registry=registry,
        ),
        model_cost=Counter(
            "incidentlens_model_cost_cny_total",
            "Estimated model cost in CNY",
            registry=registry,
        ),
        tool_calls=Counter(
            "incidentlens_tool_calls_total",
            "Read-only investigation tool calls",
            registry=registry,
        ),
        investigation_latency=Histogram(
            "incidentlens_investigation_duration_seconds",
            "End-to-end investigation latency",
            registry=registry,
        ),
    )
    tracer = configure_tracer("incidentlens-api")

    @app.middleware("http")
    async def observe_request(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)
        started = perf_counter()
        with tracer.start_as_current_span("http.request") as span:
            span.set_attribute("http.request.method", request.method)
            try:
                response = await call_next(request)
            except Exception:
                requests.labels(method=request.method, status="500").inc()
                raise
            requests.labels(method=request.method, status=str(response.status_code)).inc()
            latency.labels(method=request.method).observe(perf_counter() - started)
            span.set_attribute("http.response.status_code", response.status_code)
            if (
                request.headers.get("authorization") is not None
                or request.query_params.get("ticket") is not None
            ):
                response.headers["Cache-Control"] = "no-store"
            return response

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    return telemetry
