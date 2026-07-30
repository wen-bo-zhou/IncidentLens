# IncidentLens

Evidence-first AI production incident investigation assistant. It correlates logs, metrics, traces and runbooks, produces evidence-linked root-cause hypotheses, and gates remediation behind a simulated approval flow.

## What is implemented

- 3 showcase incidents and 12 hidden evaluation variants.
- Bounded investigation workflow with durable stage events.
- Log, metric, trace and runbook tools.
- OpenAI-compatible `qwen-plus` model gateway with an offline deterministic fallback.
- FastAPI REST/SSE API, idempotent live runs, SQLite development storage and PostgreSQL/pgvector production configuration.
- Guest/runner/admin roles, daily live-run quota, import validation and sandbox approval.
- Database-backed per-runner daily quota, paginated investigation history and an admin-only audit ledger.
- Runner-protected live reports and short-lived, investigation-scoped SSE tickets stored only as hashes.
- Named multi-credential access, production startup validation and configurable exact-origin CORS.
- Runner-owned investigation access with administrator-wide operational visibility and identity-scoped idempotency.
- Private imported-incident catalog: anonymous users see only built-in demos; Runner/Admin credentials unlock imported cases without creating public replays.
- Durable per-client authentication-failure throttling with trusted-proxy parsing, HMAC identifiers and `Retry-After` responses.
- Optional OIDC JWT federation with strict issuer/audience validation, cached JWKS rotation and IdP-group-to-role mapping.
- Browser enterprise SSO with Authorization Code + PKCE S256, nonce-bound ID-token validation, opaque server sessions, logout and CSRF protection.
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
uv run uvicorn incidentlens.app:app --reload --no-proxy-headers
```

```powershell
pnpm dev
```

Open `http://localhost:3000`. Without `MODEL_API_KEY`, the application runs the deterministic, fully auditable offline investigation path.

Administrators can open `http://localhost:3000/operations` to filter durable
investigation history and audit events. With browser SSO configured, an Admin
session opens it directly. Static credentials remain an optional in-memory
break-glass path and are cleared on refresh.

Live investigation details require a runner or administrator token. The web
client exchanges that credential for a five-minute SSE ticket, uses it only for
the selected investigation stream, and falls back to authenticated polling if
the stream disconnects. Public demo replays remain anonymous and model-free.
Authenticated responses are marked `Cache-Control: no-store`.

Imported production incidents are private and live-only. Use **打开私有目录**
with a Runner or Admin credential to load them; the credential is used for that
request and is not persisted by the browser. Restarting the API never adds
imported incidents to the anonymous replay cache.

For a public deployment, set `APP_ENV=production` and either replace
`RUNNER_TOKEN`/`ADMIN_TOKEN` with unique values of at least 32 characters, or
provide JSON maps through `RUNNER_CREDENTIALS` and `ADMIN_CREDENTIALS`. Named
credentials appear as actors in the audit ledger. Set `CORS_ORIGINS` to a JSON
array of exact browser origins; wildcard origins are rejected.

Enterprise identity providers can issue API access tokens. Configure
`OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL` and JSON arrays in
`OIDC_RUNNER_GROUPS` / `OIDC_ADMIN_GROUPS`. Tokens must be RS256-signed
`at+jwt` access tokens with matching issuer, audience, expiry and group claims.

For browser SSO, also register IncidentLens as an OIDC confidential web client
and configure `OIDC_AUTHORIZATION_URL`, `OIDC_TOKEN_URL`, `OIDC_CLIENT_ID`,
`OIDC_CLIENT_SECRET` and the exact public
`OIDC_REDIRECT_URI=https://incidentlens.example.com/api/v1/auth/callback`.
The web app uses Authorization Code + PKCE S256; the API validates both the
access token and nonce-bound ID token, then discards them and gives the browser
only an opaque `HttpOnly`, `SameSite=Strict` session cookie. Deploy Web and API
under one public origin, as in the provided Next.js proxy and Caddy setup.
Login starts are durably rate-limited by client and pending transactions are
capped globally and per client; tune the `OIDC_LOGIN_*` limits for the expected
workforce and identity-provider latency.

Set `STATIC_AUTH_ENABLED=false` to remove the legacy token path, or leave it
enabled for separately managed break-glass credentials. Token fields are shown
only when the active enterprise role is insufficient or SSO is unavailable;
entered values remain in component memory.

Authentication failures are limited per client across API instances using the
database-backed fixed window. Production requires a unique
`RATE_LIMIT_SECRET` generated from at least 32 random bytes as unpadded
base64url (for example, `python -c "import secrets; print(secrets.token_urlsafe(32))"`).
Configure
`TRUSTED_PROXY_CIDRS` for the reverse proxies allowed to supply
`X-Forwarded-For`; untrusted forwarding headers are ignored.

Each Runner can list, read, stream and cancel only investigations created by
that named identity. Administrators retain access to every investigation.
Idempotency keys are isolated per identity, so different operators can safely
reuse the same client-generated key.

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

管理员可以打开 `/operations` 查看可筛选的调查历史和审计轨迹；Runner 每日配额已持久化到数据库，服务重启或多 Worker 部署不会重置计数。浏览器可通过授权码 + PKCE 登录，访问令牌和 ID Token 只在回调时由服务端验证并立即丢弃，浏览器仅持有 HttpOnly 会话 Cookie；写请求还必须携带 CSRF 头。事件流使用五分钟有效、绑定单次调查且数据库只保存哈希的短期票据。生产模式会拒绝演示、弱口令、跨角色重复凭证和通配 CORS，并支持用命名凭证区分值班人员。

导入的生产事故默认属于私有目录，匿名访问只能看到内置演示；Runner/Admin
令牌可以临时解锁私有目录，但导入事故不会生成公开回放，服务重启后也不会改变这一边界。
无效认证尝试会按客户端跨实例持久限流；只有可信代理网段提供的转发地址会被采信，
数据库仅保存使用生产 HMAC 密钥生成的不可逆客户端标识。
