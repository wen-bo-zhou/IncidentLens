# IncidentLens architecture

IncidentLens uses a bounded evidence workflow instead of an open-ended agent loop. FastAPI owns public contracts and durable investigation state; Celery executes live runs; PostgreSQL stores imported packs, pgvector runbook chunks, reports, ordered events and approvals; Redis carries jobs; Next.js renders replay, live investigation and evaluation views.

The workflow is `collecting → timeline_building → hypothesizing → verifying → ranking → reporting`. Every important claim references a stable evidence ID. The model may rewrite the auditable narrative when an OpenAI-compatible API key is configured, but root-cause ranking and quality gates remain deterministic.

Public replay is intentionally model-free. Live mode is role-gated, idempotent, limited to ten runs per runner per day, capped at ¥0.20 before a model call, and can be disabled without affecting the portfolio demo. Celery late acknowledgements plus event uniqueness make Worker-loss recovery safe; SSE streams poll durable events and honor `Last-Event-ID`.

Operational governance is database-backed. Runner identity is represented only
by a SHA-256 token digest in the daily quota table, and quota consumption uses
an atomic conditional update so restarts and multiple API workers share the same
limit. Runner/admin users can read paginated investigation history; only admins
can read the filtered audit ledger exposed by the `/operations` console.
