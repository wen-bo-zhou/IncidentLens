import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/app-shell";
import { api } from "@/lib/api";
import type {
  IncidentCase,
  InvestigationDetail,
  InvestigationReport,
  WorkflowEvent,
} from "@/lib/types";

vi.mock("@/lib/api", () => ({
  api: {
    incidents: vi.fn(),
    replay: vi.fn(),
    createInvestigation: vi.fn(),
    investigation: vi.fn(),
    streamTicket: vi.fn(),
    cancelInvestigation: vi.fn(),
    approveRemediation: vi.fn(),
    eventsUrl: vi.fn(),
  },
}));

const incident: IncidentCase = {
  id: "case-1",
  title: "Checkout latency",
  summary: "Latency increased after a deployment.",
  scenario_family: "deployment_config",
  visibility: "showcase",
  starts_at: "2026-01-10T09:00:00Z",
  ends_at: "2026-01-10T10:00:00Z",
  services: ["checkout"],
  evidence_count: 1,
  replay_available: true,
  severity: "SEV-2",
};

const replayReport: InvestigationReport = {
  investigation_id: "replay-case-1",
  summary: "Deployment configuration is supported.",
  timeline: [],
  ranked_hypotheses: [
    {
      id: "hyp-1",
      title: "Deployment configuration",
      root_cause_category: "deployment_config",
      causal_chain: ["deploy", "latency"],
      supporting_evidence_ids: ["ev-1"],
      contradicting_evidence_ids: [],
      missing_evidence: [],
      score: 0.9,
      confidence: "high",
      status: "supported",
    },
  ],
  confirmed_facts: ["Latency increased."],
  uncertainties: [],
  recommended_actions: [],
  evidence_index: [],
  model_usage: {
    provider: "offline",
    model: "evidence-rules-v1",
    prompt_tokens: 0,
    completion_tokens: 0,
    model_calls: 0,
    tool_calls: 1,
  },
  total_cost_cny: 0,
  total_latency_ms: 10,
};

const inconclusiveReport: InvestigationReport = {
  ...replayReport,
  investigation_id: "inv-1",
  summary: "The selected window does not contain enough evidence.",
  ranked_hypotheses: [],
  confirmed_facts: [],
  uncertainties: ["Collect logs for the selected window."],
};

class FakeEventSource {
  static latest: FakeEventSource | undefined;

  onerror: ((event: Event) => void) | null = null;
  private listeners = new Map<string, (event: MessageEvent<string>) => void>();

  constructor(public readonly url: string | URL) {
    FakeEventSource.latest = this;
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
    this.listeners.set(type, listener as (event: MessageEvent<string>) => void);
  }

  close() {}

  emit(type: string, event: WorkflowEvent) {
    this.listeners.get(type)?.({ data: JSON.stringify(event) } as MessageEvent<string>);
  }

  fail() {
    this.onerror?.(new Event("error"));
  }
}

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AppShell />
    </QueryClientProvider>,
  );
}

describe("AppShell", () => {
  const mockedApi = vi.mocked(api);

  beforeEach(() => {
    vi.clearAllMocks();
    FakeEventSource.latest = undefined;
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("crypto", { randomUUID: () => "request-1" });
    mockedApi.incidents.mockResolvedValue([incident]);
    mockedApi.replay.mockResolvedValue(replayReport);
    mockedApi.createInvestigation.mockResolvedValue({
      investigation_id: "inv-1",
      status: "queued",
      mode: "live",
      idempotent_replay: false,
    });
    mockedApi.streamTicket.mockResolvedValue({
      ticket: "stream-ticket",
      expires_at: "2026-07-27T12:05:00Z",
    });
    mockedApi.eventsUrl.mockReturnValue("/api/v1/investigations/inv-1/events");
  });

  it("polls the terminal report when the event stream disconnects", async () => {
    const user = userEvent.setup();
    const detail: InvestigationDetail = {
      investigation_id: "inv-1",
      incident_case_id: incident.id,
      mode: "live",
      status: "inconclusive",
      report: inconclusiveReport,
      remediation_proposals: [],
    };
    mockedApi.investigation.mockResolvedValue(detail);
    renderApp();

    await user.click(await screen.findByRole("button", { name: "实时调查" }));
    await user.type(screen.getByLabelText("Runner 令牌"), "runner-token");
    await user.click(screen.getByRole("button", { name: "确认启动" }));
    await waitFor(() => expect(FakeEventSource.latest).toBeDefined());
    expect(mockedApi.streamTicket).toHaveBeenCalledWith("inv-1", "runner-token");
    expect(mockedApi.eventsUrl).toHaveBeenCalledWith("inv-1", "stream-ticket");

    act(() => FakeEventSource.latest?.fail());

    expect(
      await screen.findByRole("heading", { name: "证据不足，无法判定根因" }),
    ).toBeInTheDocument();
    expect(screen.getByText("inconclusive")).toBeInTheDocument();
    expect(mockedApi.investigation).toHaveBeenCalledWith("inv-1", "runner-token");
  });

  it("does not request a replay for an imported live-only incident", async () => {
    mockedApi.incidents.mockResolvedValue([
      { ...incident, id: "imported-case", replay_available: false },
    ]);

    renderApp();

    expect(
      await screen.findByRole("heading", { name: "Checkout latency" }),
    ).toBeInTheDocument();
    expect(mockedApi.replay).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "实时调查" })).toBeEnabled();
  });
});
