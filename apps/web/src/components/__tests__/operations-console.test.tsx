import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OperationsConsole } from "@/components/operations-console";
import { useAuth } from "@/components/auth-context";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  api: {
    credentialSession: vi.fn(),
    investigation: vi.fn(),
    investigationHistory: vi.fn(),
    auditEvents: vi.fn(),
  },
}));
vi.mock("@/components/auth-context", () => ({
  useAuth: vi.fn(),
}));

function renderConsole() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const result = render(
    <QueryClientProvider client={queryClient}>
      <OperationsConsole />
    </QueryClientProvider>,
  );
  return { ...result, queryClient };
}

describe("OperationsConsole", () => {
  const mockedApi = vi.mocked(api);
  const mockedUseAuth = vi.mocked(useAuth);

  beforeEach(() => {
    vi.clearAllMocks();
    mockedApi.credentialSession.mockResolvedValue({
      authenticated: true,
      sso_enabled: false,
      role: "admin",
      actor: "admin",
    });
    mockedApi.investigation.mockResolvedValue({
      investigation_id: "inv-1",
      incident_case_id: "checkout-timeout",
      mode: "live",
      status: "completed",
      report: {
        investigation_id: "inv-1",
        summary: "发布配置导致支付超时。",
        timeline: [
          {
            timestamp: "2026-07-27T09:00:00Z",
            category: "deployment",
            description: "连接池上限由 50 降为 5",
            evidence_ids: ["metric-pool"],
          },
        ],
        ranked_hypotheses: [
          {
            id: "hyp-1",
            title: "数据库连接池耗尽",
            root_cause_category: "db_pool_exhaustion",
            causal_chain: ["错误配置降低连接池上限", "请求等待连接并超时"],
            supporting_evidence_ids: ["metric-pool"],
            contradicting_evidence_ids: [],
            missing_evidence: [],
            score: 0.96,
            confidence: "high",
            status: "supported",
          },
        ],
        confirmed_facts: ["连接等待时间在发布后升高"],
        uncertainties: ["需要确认数据库代理的连接上限"],
        recommended_actions: [
          {
            action_type: "restore_pool_limit",
            title: "恢复连接池上限",
            rationale: "解除请求等待并恢复吞吐。",
            risk: "medium",
            requires_approval: true,
          },
        ],
        evidence_index: [
          {
            id: "metric-pool",
            kind: "metric",
            timestamp: "2026-07-27T09:00:00Z",
            service: "checkout",
            source: "prometheus",
            locator: "db_pool_waiting",
            excerpt: "waiting=42",
            content_hash: "a".repeat(64),
            attributes: {},
          },
        ],
        model_usage: {
          provider: "offline",
          model: "evidence-rules-v1",
          prompt_tokens: 0,
          completion_tokens: 0,
          model_calls: 0,
          tool_calls: 4,
        },
        total_cost_cny: 0,
        total_latency_ms: 320,
      },
      remediation_proposals: [],
    });
    mockedApi.investigationHistory.mockResolvedValue({
      items: [
        {
          investigation_id: "inv-1",
          incident_case_id: "checkout-timeout",
          mode: "live",
          status: "completed",
          summary: "发布配置导致支付超时。",
          created_at: "2026-07-27T09:00:00Z",
          updated_at: "2026-07-27T09:01:00Z",
        },
      ],
      total: 1,
      limit: 20,
      offset: 0,
    });
    mockedApi.auditEvents.mockResolvedValue({
      items: [
        {
          id: 7,
          actor: "runner",
          action: "investigation.created",
          resource_id: "inv-1",
          detail: { case_id: "checkout-timeout" },
          created_at: "2026-07-27T09:00:00Z",
        },
      ],
      total: 1,
      limit: 20,
      offset: 0,
    });
    mockedUseAuth.mockReturnValue({
      session: {
        authenticated: false,
        sso_enabled: false,
        role: "guest",
        actor: null,
      },
      isLoading: false,
      error: null,
      logout: vi.fn(),
    });
  });

  it("loads investigation and audit ledgers after admin authentication", async () => {
    const user = userEvent.setup();
    renderConsole();

    await user.type(screen.getByLabelText("Runner 或 Admin 令牌"), "admin-token");
    await user.click(screen.getByRole("button", { name: "查看调查历史" }));

    expect(
      await screen.findByRole("heading", { name: "发布配置导致支付超时。" }),
    ).toBeInTheDocument();
    expect(screen.getByText("investigation.created")).toBeInTheDocument();
    expect(screen.getByText("checkout-timeout")).toBeInTheDocument();
    expect(mockedApi.investigationHistory).toHaveBeenCalledWith("admin-token", {
      status: undefined,
      limit: 20,
      offset: 0,
    });
    expect(mockedApi.auditEvents).toHaveBeenCalledWith("admin-token", {
      action: undefined,
      limit: 20,
      offset: 0,
    });
  });

  it("applies a status filter to the investigation ledger", async () => {
    const user = userEvent.setup();
    renderConsole();

    await user.type(screen.getByLabelText("Runner 或 Admin 令牌"), "admin-token");
    await user.click(screen.getByRole("button", { name: "查看调查历史" }));
    await screen.findByText("investigation.created");
    await user.selectOptions(screen.getByLabelText("运行状态"), "failed");

    await waitFor(() =>
      expect(mockedApi.investigationHistory).toHaveBeenLastCalledWith(
        "admin-token",
        {
          status: "failed",
          limit: 20,
          offset: 0,
        },
      ),
    );
  });

  it("removes cached credentials when the operator clears the token", async () => {
    const user = userEvent.setup();
    const { queryClient } = renderConsole();

    await user.type(screen.getByLabelText("Runner 或 Admin 令牌"), "admin-token");
    await user.click(screen.getByRole("button", { name: "查看调查历史" }));
    await screen.findByText("investigation.created");
    expect(
      queryClient.getQueryCache().findAll({ queryKey: ["operations"] }),
    ).not.toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "清除令牌" }));

    expect(screen.getByRole("heading", { name: "查看调查历史" })).toBeInTheDocument();
    expect(
      queryClient.getQueryCache().findAll({ queryKey: ["operations"] }),
    ).toHaveLength(0);
  });

  it("never places a static credential in React Query cache keys", async () => {
    const user = userEvent.setup();
    const { queryClient } = renderConsole();

    await user.type(
      screen.getByLabelText("Runner 或 Admin 令牌"),
      "private-admin-token",
    );
    await user.click(screen.getByRole("button", { name: "查看调查历史" }));
    await screen.findByText("investigation.created");

    const cachedKeys = queryClient
      .getQueryCache()
      .getAll()
      .map((query) => query.queryKey);
    expect(JSON.stringify(cachedKeys)).not.toContain("private-admin-token");
  });

  it("removes credential-bearing query closures when leaving the page", async () => {
    const user = userEvent.setup();
    const { queryClient, unmount } = renderConsole();

    await user.type(
      screen.getByLabelText("Runner 或 Admin 令牌"),
      "private-admin-token",
    );
    await user.click(screen.getByRole("button", { name: "查看调查历史" }));
    await screen.findByText("investigation.created");

    unmount();

    await waitFor(() =>
      expect(
        queryClient.getQueryCache().findAll({ queryKey: ["operations"] }),
      ).toHaveLength(0),
    );
  });

  it("opens automatically for an enterprise admin session", async () => {
    mockedUseAuth.mockReturnValue({
      session: {
        authenticated: true,
        sso_enabled: true,
        role: "admin",
        actor: "oidc-admin",
      },
      isLoading: false,
      error: null,
      logout: vi.fn(),
    });

    renderConsole();

    expect(
      await screen.findByRole("heading", { name: "发布配置导致支付超时。" }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Runner 或 Admin 令牌")).not.toBeInTheDocument();
    expect(mockedApi.investigationHistory).toHaveBeenCalledWith(undefined, {
      status: undefined,
      limit: 20,
      offset: 0,
    });
    expect(mockedApi.auditEvents).toHaveBeenCalledWith(undefined, {
      action: undefined,
      limit: 20,
      offset: 0,
    });
  });

  it("opens a runner's own investigation history without requesting the audit ledger", async () => {
    mockedUseAuth.mockReturnValue({
      session: {
        authenticated: true,
        sso_enabled: true,
        role: "runner",
        actor: "oidc-runner",
      },
      isLoading: false,
      error: null,
      logout: vi.fn(),
    });

    renderConsole();

    expect(
      await screen.findByRole("heading", { name: "发布配置导致支付超时。" }),
    ).toBeInTheDocument();
    expect(screen.getByText("仅显示你创建的调查")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "审计轨迹" })).not.toBeInTheDocument();
    expect(mockedApi.auditEvents).not.toHaveBeenCalled();
  });

  it("validates a static runner credential before opening its history", async () => {
    const user = userEvent.setup();
    mockedApi.credentialSession.mockResolvedValue({
      authenticated: true,
      sso_enabled: false,
      role: "runner",
      actor: "on-call-runner",
    });
    renderConsole();

    await user.type(screen.getByLabelText("Runner 或 Admin 令牌"), "runner-token");
    await user.click(screen.getByRole("button", { name: "查看调查历史" }));

    expect(
      await screen.findByRole("heading", { name: "发布配置导致支付超时。" }),
    ).toBeInTheDocument();
    expect(mockedApi.credentialSession).toHaveBeenCalledWith("runner-token");
    expect(mockedApi.auditEvents).not.toHaveBeenCalled();
  });

  it("reopens a completed investigation report from durable history", async () => {
    const user = userEvent.setup();
    mockedUseAuth.mockReturnValue({
      session: {
        authenticated: true,
        sso_enabled: true,
        role: "admin",
        actor: "oidc-admin",
      },
      isLoading: false,
      error: null,
      logout: vi.fn(),
    });
    renderConsole();

    const openReportButton = await screen.findByRole("button", {
      name: "打开报告 inv-1",
    });
    await user.click(openReportButton);

    const rootCause = await screen.findByRole("heading", {
      name: "数据库连接池耗尽",
    });
    const dialog = screen.getByRole("dialog", {
      name: "发布配置导致支付超时。",
    });
    expect(dialog).toBeInTheDocument();
    await waitFor(() =>
      expect(
        within(dialog).getByRole("heading", { name: "发布配置导致支付超时。" }),
      ).toHaveFocus(),
    );
    expect(rootCause).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "因果时间线" })).toBeInTheDocument();
    expect(screen.getByText("连接池上限由 50 降为 5")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "建议处置" })).toBeInTheDocument();
    expect(screen.getByText("恢复连接池上限")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "证据索引" })).toBeInTheDocument();
    expect(screen.getByText("waiting=42")).toBeInTheDocument();
    expect(screen.getByText("需要确认数据库代理的连接上限")).toBeInTheDocument();
    expect(screen.getByText("连接等待时间在发布后升高")).toBeInTheDocument();
    expect(mockedApi.investigation).toHaveBeenCalledWith("inv-1", undefined);

    const operationsGrid = openReportButton.closest(".operations-grid");
    const closeButton = within(dialog).getByRole("button", {
      name: "关闭历史报告",
    });
    expect(operationsGrid).toHaveAttribute("inert");
    await user.tab();
    expect(closeButton).toHaveFocus();
    await user.tab();
    expect(closeButton).toHaveFocus();
    await user.tab({ shift: true });
    expect(closeButton).toHaveFocus();

    await user.keyboard("{Escape}");
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(openReportButton).toHaveFocus();
    expect(operationsGrid).not.toHaveAttribute("inert");
  });

  it("renders explicit empty states for incomplete report sections", async () => {
    const detail = await mockedApi.investigation("inv-1");
    mockedApi.investigation.mockClear();
    mockedApi.investigation.mockResolvedValue({
      ...detail,
      report: detail.report
        ? {
            ...detail.report,
            ranked_hypotheses: [],
            recommended_actions: [],
            evidence_index: [],
          }
        : null,
    });
    mockedUseAuth.mockReturnValue({
      session: {
        authenticated: true,
        sso_enabled: true,
        role: "admin",
        actor: "oidc-admin",
      },
      isLoading: false,
      error: null,
      logout: vi.fn(),
    });
    const user = userEvent.setup();
    renderConsole();

    await user.click(
      await screen.findByRole("button", { name: "打开报告 inv-1" }),
    );

    expect(await screen.findByText("没有可用的根因假设。")).toBeInTheDocument();
    expect(screen.getByText("没有建议处置。")).toBeInTheDocument();
    expect(screen.getByText("没有可用的证据。")).toBeInTheDocument();
  });
});
