import type {
  AuthSession,
  AuditEvent,
  EvaluationSummary,
  IncidentCase,
  InvestigationDetail,
  InvestigationReport,
  InvestigationSummary,
  InvestigationWindow,
  Page,
  StreamTicket,
} from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function queryString(
  values: Record<string, string | number | undefined>,
): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  return query.toString();
}

function headerRecord(headers?: HeadersInit): Record<string, string> {
  if (!headers) return {};
  if (headers instanceof Headers) {
    return Object.fromEntries(headers.entries());
  }
  if (Array.isArray(headers)) {
    return Object.fromEntries(headers);
  }
  return { ...headers };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isMultipart =
    typeof FormData !== "undefined" && init?.body instanceof FormData;
  const method = (init?.method ?? "GET").toUpperCase();
  const csrfHeaders: Record<string, string> = SAFE_METHODS.has(method)
    ? {}
    : { "X-IncidentLens-CSRF": "1" };
  const providedHeaders = headerRecord(init?.headers);
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: isMultipart
      ? { ...csrfHeaders, ...providedHeaders }
      : {
          "Content-Type": "application/json",
          ...csrfHeaders,
          ...providedHeaders,
        },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(detail.detail ?? `请求失败：${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function authHeaders(token?: string): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export const api = {
  session: () => request<AuthSession>("/api/v1/auth/session"),
  credentialSession: (token: string) =>
    request<AuthSession>("/api/v1/auth/session", {
      headers: authHeaders(token),
    }),
  loginUrl: (returnTo: string) =>
    `${API_URL}/api/v1/auth/login?${queryString({ return_to: returnTo })}`,
  logout: () =>
    request<void>("/api/v1/auth/logout", {
      method: "POST",
    }),
  incidents: (token?: string) =>
    request<IncidentCase[]>(
      "/api/v1/incidents",
      token
        ? { headers: authHeaders(token) }
        : undefined,
    ),
  importIncident: (file: File, adminToken?: string) => {
    const body = new FormData();
    body.append("file", file);
    return request<IncidentCase>("/api/v1/incidents/import", {
      method: "POST",
      headers: authHeaders(adminToken),
      body,
    });
  },
  replay: (caseId: string) =>
    request<InvestigationReport>(`/api/v1/demo/replays/${encodeURIComponent(caseId)}`),
  createInvestigation: (
    caseId: string,
    runnerToken: string | undefined,
    idempotencyKey: string,
    window: InvestigationWindow,
  ) =>
    request<{
      investigation_id: string;
      status: string;
      mode: "live";
      idempotent_replay: boolean;
    }>("/api/v1/investigations", {
      method: "POST",
      headers: {
        ...authHeaders(runnerToken),
        "Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify({
        incident_case_id: caseId,
        mode: "live",
        start_at: window.startAt,
        end_at: window.endAt,
      }),
    }),
  investigation: (investigationId: string, runnerToken?: string) =>
    request<InvestigationDetail>(
      `/api/v1/investigations/${encodeURIComponent(investigationId)}`,
      { headers: authHeaders(runnerToken) },
    ),
  streamTicket: (investigationId: string, runnerToken?: string) =>
    request<StreamTicket>(
      `/api/v1/investigations/${encodeURIComponent(investigationId)}/stream-ticket`,
      {
        method: "POST",
        headers: authHeaders(runnerToken),
      },
    ),
  cancelInvestigation: (investigationId: string, runnerToken?: string) =>
    request<{ status: "canceled" }>(
      `/api/v1/investigations/${encodeURIComponent(investigationId)}/cancel`,
      {
        method: "POST",
        headers: authHeaders(runnerToken),
      },
    ),
  approveRemediation: (
    investigationId: string,
    proposalId: string,
    adminToken?: string,
  ) =>
    request<{ proposal_id: string; status: string; simulated_change: Record<string, unknown> }>(
      `/api/v1/investigations/${encodeURIComponent(investigationId)}/remediations/${encodeURIComponent(proposalId)}/approve`,
      {
        method: "POST",
        headers: authHeaders(adminToken),
      },
    ),
  eventsUrl: (investigationId: string, ticket: string) =>
    `${API_URL}/api/v1/investigations/${encodeURIComponent(investigationId)}/events?${queryString({ ticket })}`,
  evaluation: (adminToken?: string) =>
    request<EvaluationSummary>("/api/v1/eval-runs", {
      method: "POST",
      headers: authHeaders(adminToken),
    }),
  investigationHistory: (
    token: string | undefined,
    filters: {
      status?: string;
      caseId?: string;
      limit: number;
      offset: number;
    },
  ) =>
    request<Page<InvestigationSummary>>(
      `/api/v1/investigations?${queryString({
        limit: filters.limit,
        offset: filters.offset,
        status: filters.status,
        case_id: filters.caseId,
      })}`,
      { headers: authHeaders(token) },
    ),
  auditEvents: (
    adminToken: string | undefined,
    filters: {
      action?: string;
      resourceId?: string;
      limit: number;
      offset: number;
    },
  ) =>
    request<Page<AuditEvent>>(
      `/api/v1/audit-events?${queryString({
        limit: filters.limit,
        offset: filters.offset,
        action: filters.action,
        resource_id: filters.resourceId,
      })}`,
      { headers: authHeaders(adminToken) },
    ),
};
