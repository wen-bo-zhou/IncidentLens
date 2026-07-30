# Threat model

## Trust boundaries

- Logs, traces and runbooks are untrusted evidence, not instructions.
- Browser SSO receives only an opaque session cookie; IdP tokens remain inside the callback request path and are discarded after validation.
- The model gateway never receives server secrets and does not expose arbitrary tools.
- Remediation is allowlisted, persisted, single-use and simulated only.

## Controls

- Strict JSON/Pydantic validation, content-hash/reference/time checks, path rejection, 50 MB import cap and JSON-only uploads.
- No arbitrary URLs, SQL, shell or code execution.
- Secret redaction before model use; Prometheus labels exclude paths and content.
- Guest replay, runner quota and admin-only import/evaluation/approval.
- Runner/admin authorization for live reports; short-lived, investigation-scoped SSE tickets persisted only as SHA-256 digests.
- Constant-time credential checks, named audit principals and production rejection of demo, weak or duplicate credentials.
- OIDC access tokens require RS256, `at+jwt`, exact issuer/audience/time validation, streamed and cached JWKS, 2048-bit keys, collision-resistant `(iss, sub)` identities and explicit non-overlapping group-to-role mappings.
- Browser OIDC uses one-time state bound to a separate `SameSite=Lax` transaction cookie, PKCE S256, nonce-bound ID tokens, subject/access-token binding and bounded non-redirecting token exchange.
- Server sessions persist only random-token digests and absolute expiry; production cookies are `Secure`, `HttpOnly`, `SameSite=Strict`, host-only and cleared on logout.
- Unsafe Cookie-authenticated methods require a non-simple CSRF header; explicit Bearer credentials take precedence and cannot silently fall back to Cookie authentication.
- Exact-origin credentialed CORS and `no-store` on authenticated responses.
- Owner-scoped Runner history, report access, stream-ticket issuance, cancellation and idempotency keys; administrators retain global access.
- Imported incidents are excluded from anonymous catalog/detail responses and the public replay cache across restarts; Runner/Admin credentials are required to discover them.
- Invalid supplied credentials are rate-limited per HMAC client identifier in durable storage; forwarded addresses are accepted only from configured trusted proxy networks.
- Idempotent request/result persistence, durable audit events and one-time remediation state transition.

SSE tickets travel in the event-stream query string because browser
`EventSource` cannot set an authorization header. They expire after five
minutes, are never written in raw form to the database or audit ledger, and must
be redacted from API and reverse-proxy access logs. IncidentLens installs a
Uvicorn access-log filter; OIDC callback `code` and `state` values are filtered
the same way. Public deployments must apply equivalent filtering to any
additional proxy or ingress logs.

Authorization codes, PKCE verifiers, nonces and login state are short-lived but
sensitive. Login transactions are browser-bound and consumed before token
exchange, so callback replay cannot mint another session. A provider denial
also consumes the matching state. Return redirects are selected from a fixed
application-path allowlist, preventing an IdP callback from becoming an open
redirect.
Unauthenticated login starts are protected by a durable per-client fixed-window
limit whose storage has a hard global cardinality cap, plus serialized global
and per-client pending-transaction caps. Token responses have independent
short-read, five-second total-time and 1 MB limits, preventing slow-drip or
oversized IdP responses from holding callback workers indefinitely.
