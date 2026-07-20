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
- Idempotent request/result persistence, durable audit events and one-time remediation state transition.
