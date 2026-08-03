# Operations runbook / 运维手册

## 项目状态与剩余事项

IncidentLens `v1.0.0` 的完整 MVP 开发已经完成。当前版本已经具备事故导入、
回放与实时调查、证据关联根因分析、Runner/Admin 权限隔离、企业 OIDC
登录、持久化调查历史、完整报告恢复、审计记录、评测、沙箱处置、指标和
追踪能力。后端、前端、生产构建及 Compose smoke test 均由 CI 验证。

如果暂时不上线，没有必须继续完成的开发任务。以下事项属于生产上线、
运营准备或 MVP 之后的可选增强。

### 上线前必须完成

1. **确定部署方案**
   - 选择云服务器或托管平台，确定域名、区域、预算和容量。
   - 决定使用 Docker Compose、托管容器，还是分别部署 Web、API 和 Worker。

2. **准备生产基础设施**
   - 部署 PostgreSQL、Redis、API、Celery Worker、Next.js Web 和 HTTPS
     反向代理。
   - Web 与 API 必须通过同一个公开 Origin 提供服务。

3. **配置生产环境**
   - 设置 `APP_ENV=production`、`DATABASE_URL`、`REDIS_URL`、
     `CORS_ORIGINS`、`API_PROXY_TARGET`、`RATE_LIMIT_SECRET` 和
     `TRUSTED_PROXY_CIDRS`。
   - 所有密钥都应保存在部署平台的 Secret Manager 中，不得提交到 Git。

4. **替换演示认证信息**
   - 删除 `runner-demo-token` 和 `admin-demo-token`。
   - 静态凭证必须唯一且不少于 32 个字符，不能跨角色或跨用户复用。
   - 如果只允许企业登录，设置 `STATIC_AUTH_ENABLED=false`；如果保留
     break-glass 入口，应单独管理、审计并定期轮换静态凭证。

5. **配置域名和 HTTPS**
   - 配置 DNS 和有效 TLS 证书。
   - `CORS_ORIGINS` 必须使用精确 HTTPS Origin，禁止通配符。
   - 确认公开回调地址和应用地址完全一致。

6. **配置企业身份（启用 SSO 时）**
   - 在 IdP 注册 OIDC confidential client 和 API audience。
   - 配置 Issuer、Audience、JWKS URL、Client ID、Client Secret、
     Runner/Admin 用户组及精确回调地址。
   - 确认 Runner/Admin 组不重叠，并确定会话时长和紧急撤销流程。

7. **初始化并保护生产数据库**
   - 执行 Alembic migration。
   - 上线前创建一次完整备份，并实际验证恢复。
   - 制定自动备份、保留、加密和删除策略。

8. **完成生产安全检查**
   - 确认 API 及所有代理日志会隐藏 SSE `ticket`、OIDC `code` 和
     `state`。
   - 保持 Uvicorn `--no-proxy-headers`，并只信任实际入口代理网段。
   - 验证 Runner 所有权隔离、Admin 全局权限、审计记录和凭证轮换。
   - 制定浏览器会话撤销、管理员离职和 IdP Client Secret 泄漏处理流程。

9. **执行上线验收**
   - 重新运行后端测试、前端测试、静态检查、生产构建和 Compose smoke
     test。
   - 运行 `k6 run scripts/k6-smoke.js`。
   - 导入一份经过脱敏的真实事故数据，验证 Runner、Admin、OIDC、审计、
     报告恢复和取消流程。
   - 如果启用正式模型，使用该模型重新运行隐藏评测门槛。

10. **配置监控和报警**
    - 监控 `/health/live`、`/health/ready`、`/metrics`、API 错误率、
      Worker 队列、PostgreSQL、Redis、登录失败、限流、Runner 配额和
      模型费用。
    - 配置明确的报警接收人、值班安排和处置时限。

### 推荐完成但不阻塞上线

- 创建 `v1.0.0` Git tag、GitHub Release 和发行说明。
- 为 `main` 启用分支保护，要求 CI 成功后才能合并。
- 启用依赖漏洞、静态安全和密钥扫描。
- 制定值班、故障响应、凭证轮换、审计复核和灾难恢复流程。
- 定期演练数据库恢复，并设置日志、审计记录和事故数据保留期限。
- 编写面向 Runner、Admin 和企业身份管理员的使用说明。
- 安排一次真实用户验收并记录验收结果。

### 启用模型时需要完成

模型服务不是运行 MVP 的必要条件；不配置 `MODEL_API_KEY` 时可以免费使用
确定性离线路径。如果启用外部模型：

- 配置 `MODEL_BASE_URL`、`MODEL_API_KEY`、`MODEL_NAME` 和
  `MAX_COST_CNY`。
- 确认事故数据是否允许发送到该模型服务和所在区域。
- 使用正式模型重新运行评测，确认质量、延迟和成本门槛。
- 配置调用费用、失败率和延迟报警，并准备离线降级策略。

### MVP 之后的可选增强

- 直接连接 Prometheus、Loki、Elastic、Tempo、Jaeger、Kubernetes
  和云厂商可观测性服务。
- 集成 Slack、Teams、邮件、PagerDuty、Jira、Confluence 或 Notion。
- 增加多租户、组织级隔离和更细粒度 RBAC。
- 增加调查搜索、标签、收藏、批量导出和 PDF/Markdown 事故报告。
- 增加数据保留和自动清理策略，以及更多语言和移动端体验优化。
- 在现有沙箱模拟之外增加真实处置执行器、双人审批、变更窗口和自动回滚。
- 扩展大规模性能、容灾、多区域部署和真实生产事故评测集。

### 当前无需完成

- 不需要继续补充 MVP 功能。
- 不需要购买模型服务；离线路径不需要模型密钥。
- 不需要管理员密码即可继续本地开发。
- 不需要在本机安装 Docker；可以继续使用 SQLite、`uvicorn` 和 `pnpm`。
  Docker 只在需要本地模拟完整生产栈时使用。

## Profiles and health

`docker compose up --build` starts the core Web, API, Worker, PostgreSQL, Redis and Caddy services. `docker compose --profile observability up --build` additionally starts OpenTelemetry Collector, Prometheus, Tempo and Grafana.

- Liveness: `GET /health/live`
- Readiness: `GET /health/ready`
- Metrics: `GET /metrics`
- API schema: `GET /api/v1/openapi.json`
- Session state: `GET /api/v1/auth/session`
- Browser login: `GET /api/v1/auth/login`
- OIDC callback: `GET /api/v1/auth/callback`
- Session logout: `POST /api/v1/auth/logout`

## Operations console and governance APIs

Open `/operations` with an enterprise Runner or Admin session to inspect
durable investigation history and reopen completed reports. Runner identities
see only investigations they created. Admin identities additionally see every
investigation and the audit ledger. When browser SSO is disabled or
unavailable, a separately managed Runner or Admin token remains available as
an in-memory break-glass path; refreshing or leaving the page clears it.

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
value. The API redacts `ticket`, OIDC `code` and OIDC `state` query parameters
from Uvicorn access logs;
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
OIDC_AUTHORIZATION_URL=https://idp.example.com/oauth2/authorize
OIDC_TOKEN_URL=https://idp.example.com/oauth2/token
OIDC_CLIENT_ID=incidentlens-web
OIDC_CLIENT_SECRET=replace-with-secret-manager-value
OIDC_REDIRECT_URI=https://incidentlens.example.com/api/v1/auth/callback
OIDC_SCOPES=["openid","profile"]
OIDC_LOGIN_TTL_SECONDS=600
OIDC_SESSION_TTL_SECONDS=28800
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

The browser flow is a confidential OIDC Authorization Code client with PKCE
S256. Register the redirect URI exactly; query strings and fragments are
rejected. Production authorization, token and redirect URLs must use HTTPS and
the client secret must come from the deployment secret manager. The token
endpoint is called without redirects, with a short per-read timeout, a five
second total deadline and a 1 MB response cap. IncidentLens requires an access
token and ID token, validates signatures, issuer, both audiences, expiry,
nonce, subject consistency and `at_hash` when present, and does not persist
either token or any refresh token.

The short-lived login transaction stores only state and browser-binding
digests; its PKCE verifier and nonce expire after at most 15 minutes and are
consumed once. Successful login creates an opaque random session whose database
row contains only a session digest, stable actor, role, identity digest and
absolute expiry. The browser cookie is `HttpOnly`, `SameSite=Strict`,
`Path=/`, has no `Domain`, and is `Secure` in production. Cookie-authenticated
`POST`, `PUT`, `PATCH` and `DELETE` requests require
`X-IncidentLens-CSRF: 1`. Explicit Bearer authorization always takes
precedence and an invalid Bearer token never falls back to a valid cookie.

`OIDC_LOGIN_RATE_LIMIT` and `OIDC_LOGIN_RATE_WINDOW_SECONDS` limit login starts
per HMAC-derived client identity across every API replica.
`OIDC_LOGIN_MAX_OUTSTANDING` and
`OIDC_LOGIN_MAX_OUTSTANDING_PER_CLIENT` bound unexpired login transactions;
defaults are 5,000 globally and 10 per client. Ingress rate limiting remains a
recommended outer layer.
`RATE_LIMIT_MAX_RECORDS` separately hard-caps the shared durable client-bucket
table (10,000 by default), preventing address rotation from converting the
per-client limiter into unbounded database growth. When capacity is reached,
previously unseen client buckets fail closed with HTTP 429 until stale buckets
are removed. Every bucket stores its actual window expiry and is reclaimed
before the cap is evaluated, so a one-minute login bucket cannot occupy
capacity for a longer authentication window.

Browser-session roles are snapshots of the validated login tokens. Normal IdP
group removals take effect when the session expires (eight hours by default) or
after logout. For emergency revocation, delete the affected rows from
`browser_sessions` by `identity_hash`; deleting every row revokes all browser
sessions. Perform the database change through the normal audited operations
procedure, then rotate or disable the IdP client if its trust boundary changed.

Web and API must share one public origin. The provided Next.js rewrite and
Caddy routing satisfy this boundary. If a separate frontend origin is required,
do not enable browser SSO until redirects, cookie scope and CSRF controls are
redesigned and reviewed.

Leave `STATIC_AUTH_ENABLED=true` only when separately managed static
credentials are required for break-glass access. Set it to `false` to require
OIDC for all non-guest access.

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

Compose no longer supplies a default database password. Set a generated secret
in `POSTGRES_PASSWORD` and put the same percent-encoded value in
`COMPOSE_DATABASE_URL`. Production startup rejects SQLite, weak database
passwords, and PostgreSQL connections without `sslmode=verify-full`.

The API container runs `alembic upgrade head` before serving traffic. Before an upgrade, create a backup:

```bash
docker compose exec -T postgres pg_dump -U incidentlens -Fc incidentlens > incidentlens.dump
```

The default Compose stack runs scheduled logical backups. The backup service
writes atomic custom-format dumps to the `postgres-backups` volume and deletes
dumps older than `BACKUP_RETENTION_DAYS` (14 days by default). To start only
the database and backup service:

```bash
docker compose up -d postgres postgres-backup
```

List available backups before restoring:

```bash
docker compose run --rm --entrypoint sh postgres-restore -c "ls -lh /backups"
```

Stop API and Worker traffic, choose an exact file from that list, and restore
it through the guarded restore profile:

```bash
BACKUP_FILE=/backups/incidentlens-YYYYMMDDTHHMMSSZ.dump \
  docker compose --profile restore run --rm postgres-restore
```

Run a restore drill at least quarterly against a disposable database, record
the measured recovery time, and verify investigation/audit record counts and a
sample report before declaring the drill successful. The included logical
backup service provides recoverable scheduled snapshots, not point-in-time
recovery. Production RPO requirements below the backup interval require a
managed PostgreSQL service with continuous WAL archiving (or an independently
operated WAL archive), encrypted off-site storage, and a tested timestamp-based
restore procedure.

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
