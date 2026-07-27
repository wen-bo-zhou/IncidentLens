import type {
  EvaluationSummary,
  IncidentCase,
  InvestigationDetail,
  InvestigationReport,
  InvestigationWindow,
} from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isMultipart =
    typeof FormData !== "undefined" && init?.body instanceof FormData;
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: isMultipart
      ? { ...init?.headers }
      : { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(detail.detail ?? `请求失败：${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  incidents: () => request<IncidentCase[]>("/api/v1/incidents"),
  importIncident: (file: File, adminToken: string) => {
    const body = new FormData();
    body.append("file", file);
    return request<IncidentCase>("/api/v1/incidents/import", {
      method: "POST",
      headers: { Authorization: `Bearer ${adminToken}` },
      body,
    });
  },
  replay: (caseId: string) =>
    request<InvestigationReport>(`/api/v1/demo/replays/${encodeURIComponent(caseId)}`),
  createInvestigation: (
    caseId: string,
    runnerToken: string,
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
        Authorization: `Bearer ${runnerToken}`,
        "Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify({
        incident_case_id: caseId,
        mode: "live",
        start_at: window.startAt,
        end_at: window.endAt,
      }),
    }),
  investigation: (investigationId: string) =>
    request<InvestigationDetail>(
      `/api/v1/investigations/${encodeURIComponent(investigationId)}`,
    ),
  cancelInvestigation: (investigationId: string, runnerToken: string) =>
    request<{ status: "canceled" }>(
      `/api/v1/investigations/${encodeURIComponent(investigationId)}/cancel`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${runnerToken}` },
      },
    ),
  approveRemediation: (
    investigationId: string,
    proposalId: string,
    adminToken: string,
  ) =>
    request<{ proposal_id: string; status: string; simulated_change: Record<string, unknown> }>(
      `/api/v1/investigations/${encodeURIComponent(investigationId)}/remediations/${encodeURIComponent(proposalId)}/approve`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${adminToken}` },
      },
    ),
  eventsUrl: (investigationId: string) =>
    `${API_URL}/api/v1/investigations/${encodeURIComponent(investigationId)}/events`,
  evaluation: (adminToken: string) =>
    request<EvaluationSummary>("/api/v1/eval-runs", {
      method: "POST",
      headers: { Authorization: `Bearer ${adminToken}` },
    }),
};
