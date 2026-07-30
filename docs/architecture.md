# IncidentLens architecture

IncidentLens uses a bounded evidence workflow instead of an open-ended agent loop. FastAPI owns public contracts and durable investigation state; Celery executes live runs; PostgreSQL stores imported packs, pgvector runbook chunks, reports, ordered events and approvals; Redis carries jobs; Next.js renders replay, live investigation and evaluation views.

The workflow is `collecting → timeline_building → hypothesizing → verifying → ranking → reporting`. Every important claim references a stable evidence ID. The model may rewrite the auditable narrative when an OpenAI-compatible API key is configured, but root-cause ranking and quality gates remain deterministic.

Public replay is intentionally model-free. Live mode is role-gated, idempotent, limited to ten runs per runner per day, capped at ¥0.20 before a model call, and can be disabled without affecting the portfolio demo. Celery late acknowledgements plus event uniqueness make Worker-loss recovery safe; SSE streams poll durable events and honor `Last-Event-ID`.

Live investigation reports require a runner/admin bearer credential. Because
native `EventSource` cannot attach an authorization header, the authenticated
client first requests a five-minute stream ticket. Only its SHA-256 digest,
investigation ID and expiry are persisted; the raw ticket is returned once and
is valid only for that investigation. Authenticated polling remains the fallback
when the stream cannot reconnect.

Operational governance is database-backed. Runner identity is represented only
by a SHA-256 token digest in the daily quota table, and quota consumption uses
an atomic conditional update so restarts and multiple API workers share the same
limit. Runner/admin users can read paginated investigation history; only admins
can read the filtered audit ledger exposed by the `/operations` console. The
same console is a recovery surface: Runner identities can reopen only their own
durable reports after navigation or refresh, while Admin identities can reopen
any report and retain the audit view.

Access configuration supports either one legacy token per role or named JSON
credential maps. A non-empty named map replaces the legacy token for that role;
the selected name becomes the durable audit actor while quota keys remain
one-way token digests. Production startup rejects demo, short or duplicate
credentials and accepts only an explicit exact-origin CORS allowlist.

Optional OIDC federation validates RS256 `at+jwt` access tokens against an
explicit issuer, audience and JWKS endpoint. JWKS responses are streamed with a
1 MB limit, compression is refused, fetches have a three-second total budget,
and safe keys are cached for five minutes. Refreshes occur no more than once
every 30 seconds, including during upstream failure. Mixed-provider key sets
may contain unrelated algorithms or encryption keys, but at least one
2048-bit-or-stronger RS256 verification key is required. Exact IdP group
mappings select Runner or Admin; authorization, ownership and daily quota
identity use a collision-resistant digest of the stable `(iss, sub)` pair
rather than mutable usernames or individual access-token hashes. Static
credentials can be disabled completely when OIDC is configured. An unavailable
or malformed JWKS source fails closed with HTTP 503 and `Retry-After` without
charging the client's invalid-credential limit.

Browser SSO uses IncidentLens as a same-origin backend-for-frontend. The login
endpoint creates a browser-bound, one-time transaction and redirects to the IdP
with Authorization Code, PKCE S256 and a nonce. The callback atomically
consumes that transaction, exchanges the code as a confidential client, and
validates both the API access token and ID token. Issuer, audience, signature,
time, nonce, subject and access-token binding must all agree. IdP tokens and
refresh tokens are then discarded.

The browser receives only an opaque host-only session cookie. The database
stores its SHA-256 digest with the stable OIDC actor, role, identity digest and
absolute expiry; session lifetime is capped by both configured TTL and token
expiry. `SameSite=Strict`, `HttpOnly`, production `Secure`, exact-origin CORS,
custom-header CSRF checks and Bearer-over-Cookie precedence form the browser
request boundary. Static credentials remain optional and isolated as
break-glass access.

Invalid supplied credentials pass through a database-backed fixed-window
limiter before route dispatch. Client addresses are derived from
`X-Forwarded-For` only when the direct peer belongs to `TRUSTED_PROXY_CIDRS`;
the database key is an HMAC digest rather than a raw address. The atomic
conditional update keeps the limit consistent across API workers.
Browser login starts use the same durable, privacy-preserving client identity.
A database admission lock serializes rate-limit storage cardinality checks,
expired-row cleanup, global and per-client pending-count checks, and
transaction insertion. Both the rate-limit table and login transaction table
therefore have hard bounds under distributed request floods.

Every newly created investigation persists the principal actor as its owner.
Runner history, detail reads, stream-ticket issuance and cancellation are
filtered by that owner; administrators retain a global operational view.
Idempotency uniqueness is scoped to `(owner_actor, idempotency_key)`. The
ownership migration backfills existing rows from their
`investigation.created` audit event, while rows without a recoverable owner
remain administrator-only.
