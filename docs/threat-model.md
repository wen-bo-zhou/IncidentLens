# Threat model

## Trust boundaries

- Logs, traces and runbooks are untrusted evidence, not instructions.
- Browser tokens are role credentials and must be replaced outside local demo use.
- The model gateway never receives server secrets and does not expose arbitrary tools.
- Remediation is allowlisted, persisted, single-use and simulated only.

## Controls

- Strict JSON/Pydantic validation, content-hash/reference/time checks, path rejection, 50 MB import cap and JSON-only uploads.
- No arbitrary URLs, SQL, shell or code execution.
- Secret redaction before model use; Prometheus labels exclude paths and content.
- Guest replay, runner quota and admin-only import/evaluation/approval.
- Runner/admin authorization for live reports; short-lived, investigation-scoped SSE tickets persisted only as SHA-256 digests.
- Constant-time credential checks, named audit principals and production rejection of demo, weak or duplicate credentials.
- Exact-origin credentialed CORS and `no-store` on authenticated responses.
- Idempotent request/result persistence, durable audit events and one-time remediation state transition.

SSE tickets travel in the event-stream query string because browser
`EventSource` cannot set an authorization header. They expire after five
minutes, are never written in raw form to the database or audit ledger, and must
be redacted from API and reverse-proxy access logs. IncidentLens installs a
Uvicorn access-log filter; public deployments must apply equivalent filtering
to any additional proxy or ingress logs.
