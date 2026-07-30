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
- Investigation detail: `GET /api/v1/investigations/{id}` (runner or admin)
- Stream ticket: `POST /api/v1/investigations/{id}/stream-ticket` (runner or admin)
- Event stream: `GET /api/v1/investigations/{id}/events?ticket=...`
- Audit history: `GET /api/v1/audit-events` (admin only)
- Incident catalog: `GET /api/v1/incidents` (anonymous built-in demos;
  Runner/Admin credentials additionally reveal imported incidents)
- Incident detail: `GET /api/v1/incidents/{case_id}` (anonymous built-in
  demos; imported incidents require Runner/Admin)
- Both endpoints accept `limit` and `offset`; investigations also accept
  `status` and `case_id`, while audit events accept `action` and `resource_id`.

Runner live-run usage is stored in `daily_run_usage`, keyed by UTC date and a
one-way token digest. Restarting the API does not reset the daily limit.

Imported incident packages are always private and live-only, even if their
package metadata says `visibility=showcase`. They are excluded from anonymous
catalog responses and the replay cache before and after API restarts. The
investigation console's private-catalog credential is used for one catalog
request and is not persisted in browser storage.

Runner credentials can list, read, stream and cancel only investigations owned
by their actor name. Administrator credentials can inspect every investigation.
The v0.5 ownership migration derives existing owners from
`investigation.created` audit events; legacy rows without that audit evidence
are intentionally visible only to administrators.

Stream tickets live for five minutes and are scoped to one investigation.
`investigation_stream_tickets` stores only their SHA-256 digests. Ticket
issuance is recorded as `investigation.stream_ticket_issued` without the raw
value. The API redacts the `ticket` query parameter from Uvicorn access logs;
configure any additional public reverse-proxy logs to do the same.

## Production access configuration

Set `APP_ENV=production` before exposing the live API. Startup then rejects
demo credentials, credentials shorter than 32 characters, credentials reused
across actors or roles, actor names reused across roles, unsafe actor names,
and wildcard or non-origin CORS entries.

For OIDC JWT federation, register IncidentLens as an API audience in the
identity provider and configure exact trust values plus group mappings:

```dotenv
STATIC_AUTH_ENABLED=false
OIDC_ISSUER=https://idp.example.com
OIDC_AUDIENCE=incidentlens-api
OIDC_JWKS_URL=https://idp.example.com/.well-known/jwks.json
OIDC_GROUPS_CLAIM=groups
OIDC_RUNNER_GROUPS=["incidentlens-runners"]
OIDC_ADMIN_GROUPS=["incidentlens-admins"]
```

The API accepts only RS256-signed `at+jwt` access tokens containing `iss`,
`sub`, `aud`, `iat`, `exp` and the configured top-level group claim. RSA
verification keys must be at least 2048 bits. The JWKS document is limited to
100 keys / 1 MB, streamed without compression under a three-second total fetch
budget, cached for five minutes and protected by a 30-second refresh cooldown.
Unrelated algorithm and encryption keys in a mixed provider JWKS are ignored;
at least one safe RS256 verification key is required. Role mappings cannot
overlap or reuse registered identity/security claims. Investigation ownership,
audit actors and quota keys derive from a collision-resistant digest of the
stable issuer/subject pair, so token refreshes and username changes do not
create a new identity. The `oidc-` audit-actor namespace is reserved from static
credential maps. When a required JWKS refresh fails or returns an unsafe key
set, authenticated requests fail closed with HTTP 503 and `Retry-After: 30`;
these infrastructure failures do not consume the per-client invalid-credential
allowance.

Leave `STATIC_AUTH_ENABLED=true` only when separately managed static
credentials are required for break-glass access. The current web console
accepts an IdP access token in its Runner/Admin token fields; interactive
authorization-code login is a separate deployment/client concern.

For one credential per role, set unique `RUNNER_TOKEN` and `ADMIN_TOKEN`
values. For multiple operators, use JSON maps; a non-empty map replaces the
single-token setting for that role:

```dotenv
RUNNER_CREDENTIALS={"oncall-primary":"replace-with-32-plus-characters"}
ADMIN_CREDENTIALS={"security-lead":"replace-with-another-32-plus-characters"}
CORS_ORIGINS=["https://incidentlens.example.com"]
```

The map key is written to the audit ledger as the actor. Raw credentials are
never persisted, and responses to requests carrying authorization or stream
tickets are marked `Cache-Control: no-store`.

Generate `RATE_LIMIT_SECRET` from at least 32 random bytes in production:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

The value must be unpadded base64url and must not be reused across
environments. `AUTH_FAILURE_LIMIT` defaults to 10 attempts per
`AUTH_FAILURE_WINDOW_SECONDS=300`. Attempts above the limit return HTTP 429
with `Retry-After`; valid credentials remain usable. Rate-limit rows contain
only HMAC client identifiers and are shared by all API instances.

Set `TRUSTED_PROXY_CIDRS` to a JSON array containing only the networks that
directly proxy the API. The Compose profile uses `["172.16.0.0/12"]` because
the API is not published outside its private Docker network. If the API is
exposed directly, replace this range with the exact ingress network or an empty
array; never trust all Internet addresses.

IncidentLens must receive the direct socket peer unchanged so it can enforce
that allowlist. The provided API container starts Uvicorn with
`--no-proxy-headers`; preserve that setting for custom process managers.

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

Celery uses late acknowledgements and rejects tasks when a Worker is lost. A replacement Worker replays the deterministic stages; event sequence uniqueness and idempotent report/remediation writes prevent duplicates. Clients reconnect to the SSE endpoint with `Last-Event-ID` and receive only later events while the scoped stream ticket is valid; the web client uses authenticated report polling if reconnection fails.

## Load check

With the stack running, execute `k6 run scripts/k6-smoke.js`. The configured gates require less than 1% request errors and cached replay P95 below three seconds.

---

核心环境默认不会把原始 Prompt、证据全文或令牌写入 Trace。公开部署前必须替换演示令牌；若没有可接受的低成本运行环境，应只开放缓存回放，关闭实时 Runner。
