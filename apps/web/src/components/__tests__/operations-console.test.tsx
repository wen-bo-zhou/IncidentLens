import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OperationsConsole } from "@/components/operations-console";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  api: {
    investigationHistory: vi.fn(),
    auditEvents: vi.fn(),
  },
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

  beforeEach(() => {
    vi.clearAllMocks();
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
  });

  it("loads investigation and audit ledgers after admin authentication", async () => {
    const user = userEvent.setup();
    renderConsole();

    await user.type(screen.getByLabelText("管理员令牌"), "admin-token");
    await user.click(screen.getByRole("button", { name: "打开运营中心" }));

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

    await user.type(screen.getByLabelText("管理员令牌"), "admin-token");
    await user.click(screen.getByRole("button", { name: "打开运营中心" }));
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

    await user.type(screen.getByLabelText("管理员令牌"), "admin-token");
    await user.click(screen.getByRole("button", { name: "打开运营中心" }));
    await screen.findByText("investigation.created");
    expect(
      queryClient.getQueryCache().findAll({ queryKey: ["operations"] }),
    ).not.toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "清除令牌" }));

    expect(screen.getByRole("heading", { name: "打开运营中心" })).toBeInTheDocument();
    expect(
      queryClient.getQueryCache().findAll({ queryKey: ["operations"] }),
    ).toHaveLength(0);
  });
});
