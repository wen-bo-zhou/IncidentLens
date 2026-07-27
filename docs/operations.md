# Operations runbook / 运维手册

## Profiles and health

`docker compose up --build` starts the core Web, API, Worker, PostgreSQL, Redis and Caddy services. `docker compose --profile observability up --build` additionally starts OpenTelemetry Collector, Prometheus, Tempo and Grafana.

- Liveness: `GET /health/live`
- Readiness: `GET /health/ready`
- Metrics: `GET /metrics`
- API schema: `GET /api/v1/openapi.json`

## Operations console and governance APIs

Open `/operations` and provide an administrator token to inspect the durable
investigation and audit ledgers. The browser keeps the token in component memory
only; refreshing or leaving the page clears it.

- Investigation history: `GET /api/v1/investigations` (runner or admin)
- Audit history: `GET /api/v1/audit-events` (admin only)
- Both endpoints accept `limit` and `offset`; investigations also accept
  `status` and `case_id`, while audit events accept `action` and `resource_id`.

Runner live-run usage is stored in `daily_run_usage`, keyed by UTC date and a
one-way token digest. Restarting the API does not reset the daily limit.

## Database lifecycle

The API container runs `alembic upgrade head` before serving traffic. Before an upgrade, create a backup:

```bash
docker compose exec -T postgres pg_dump -U incidentlens -Fc incidentlens > incidentlens.dump
```

Restore into a stopped or empty environment:

```bash
docker compose exec -T postgres pg_restore -U incidentlens -d incidentlens --clean --if-exists < incidentlens.dump
```

Schema rollback for the initial release is destructive and should only be used against a disposable environment:

```bash
docker compose run --rm api alembic downgrade base
```

## Recovery behavior

Celery uses late acknowledgements and rejects tasks when a Worker is lost. A replacement Worker replays the deterministic stages; event sequence uniqueness and idempotent report/remediation writes prevent duplicates. Clients reconnect to the SSE endpoint with `Last-Event-ID` and receive only later events.

## Load check

With the stack running, execute `k6 run scripts/k6-smoke.js`. The configured gates require less than 1% request errors and cached replay P95 below three seconds.

---

核心环境默认不会把原始 Prompt、证据全文或令牌写入 Trace。公开部署前必须替换演示令牌；若没有可接受的低成本运行环境，应只开放缓存回放，关闭实时 Runner。
