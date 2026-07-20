# IncidentLens

Evidence-first AI production incident investigation assistant. It correlates logs, metrics, traces and runbooks, produces evidence-linked root-cause hypotheses, and gates remediation behind a simulated approval flow.

## What is implemented

- 3 showcase incidents and 12 hidden evaluation variants.
- Bounded investigation workflow with durable stage events.
- Log, metric, trace and runbook tools.
- OpenAI-compatible `qwen-plus` model gateway with an offline deterministic fallback.
- FastAPI REST/SSE API, idempotent live runs, SQLite development storage and PostgreSQL/pgvector production configuration.
- Guest/runner/admin roles, daily live-run quota, import validation and sandbox approval.
- Next.js incident console, causal-spine timeline, evidence dialog and evaluation console.
- Prometheus metrics, OpenTelemetry spans, Docker Compose and optional Grafana/Tempo profile.
- Deterministic one-shot baseline versus Agent evaluation, Markdown export and admin-approved sandbox simulation.

## Local development

Requirements: Python 3.12+, Node 24+, pnpm 11.

```powershell
python -m pip install uv
uv sync --locked --extra dev
pnpm install
Copy-Item .env.example .env
```

Start the API and web app in separate terminals:

```powershell
$env:PYTHONPATH='services/api'
uv run uvicorn incidentlens.app:app --reload
```

```powershell
pnpm dev
```

Open `http://localhost:3000`. Without `MODEL_API_KEY`, the application runs the deterministic, fully auditable offline investigation path.

## Docker

```powershell
docker compose up --build
```

Open `http://localhost:3000`. To enable the optional observability stack:

```powershell
$env:OTEL_EXPORTER_OTLP_ENDPOINT='http://otel-collector:4317'
docker compose --profile observability up --build
```

Grafana is exposed at `http://localhost:3001` and Prometheus at `http://localhost:9090`.

## Tests

```powershell
uv run pytest
uv run ruff check .
uv run mypy services/api/incidentlens
pnpm test:web
pnpm lint
pnpm typecheck
pnpm build
```

Demo credentials from `.env.example` are `runner-demo-token` and `admin-demo-token`. Replace them before any public deployment.

Detailed design and operations: [`docs/architecture.md`](docs/architecture.md), [`docs/evaluation.md`](docs/evaluation.md), [`docs/threat-model.md`](docs/threat-model.md), and [`docs/operations.md`](docs/operations.md).

---

## 中文说明

IncidentLens 是一个证据优先的 AI 生产事故调查助手。它把日志、指标、分布式 Trace 和 Runbook 放进受约束状态机，输出可追溯的因果时间线、候选根因和沙箱处置建议。

默认无需模型密钥即可回放全部演示；配置任意 OpenAI-compatible 接口后，系统会调用模型生成结构化事故叙述，但根因排名与质量门槛仍由确定性评分控制。详细设计见 `docs/architecture.md`、`docs/evaluation.md` 和 `docs/threat-model.md`。
