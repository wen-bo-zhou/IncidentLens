# Seeded incident packs

IncidentLens generates 15 deterministic incident packs in `incidentlens.scenarios`:

- 3 showcase packs: deployment timeout, database-pool exhaustion, poison message.
- 12 hidden variants: four timestamp/noise variants per family.

Each pack contains log, metric, OpenTelemetry-style trace and runbook evidence plus an isolated golden label. Normal API responses use `PublicIncidentCase` and never serialize the golden label.

