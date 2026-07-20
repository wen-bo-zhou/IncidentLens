import type {
  EvaluationSummary,
  IncidentCase,
  InvestigationDetail,
  InvestigationReport,
} from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(detail.detail ?? `请求失败：${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  incidents: () => request<IncidentCase[]>("/api/v1/incidents"),
  replay: (caseId: string) =>
    request<InvestigationReport>(`/api/v1/demo/replays/${encodeURIComponent(caseId)}`),
  createInvestigation: (caseId: string, runnerToken: string, idempotencyKey: string) =>
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
      body: JSON.stringify({ incident_case_id: caseId, mode: "live" }),
    }),
  investigation: (investigationId: string) =>
    request<InvestigationDetail>(
      `/api/v1/investigations/${encodeURIComponent(investigationId)}`,
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
