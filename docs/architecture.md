# IncidentLens architecture

IncidentLens uses a bounded evidence workflow instead of an open-ended agent loop. FastAPI owns public contracts and durable investigation state; Celery executes live runs; PostgreSQL stores imported packs, pgvector runbook chunks, reports, ordered events and approvals; Redis carries jobs; Next.js renders replay, live investigation and evaluation views.

The workflow is `collecting → timeline_building → hypothesizing → verifying → ranking → reporting`. Every important claim references a stable evidence ID. The model may rewrite the auditable narrative when an OpenAI-compatible API key is configured, but root-cause ranking and quality gates remain deterministic.

Public replay is intentionally model-free. Live mode is role-gated, idempotent, limited to ten runs per runner per day, capped at ¥0.20 before a model call, and can be disabled without affecting the portfolio demo. Celery late acknowledgements plus event uniqueness make Worker-loss recovery safe; SSE streams poll durable events and honor `Last-Event-ID`.
