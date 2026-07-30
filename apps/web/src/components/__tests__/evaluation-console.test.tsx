import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuth } from "@/components/auth-context";
import { EvaluationConsole } from "@/components/evaluation-console";
import { api } from "@/lib/api";

vi.mock("@/components/auth-context", () => ({
  useAuth: vi.fn(),
}));
vi.mock("@/lib/api", () => ({
  api: {
    evaluation: vi.fn(),
    loginUrl: vi.fn(
      (returnTo: string) =>
        `/api/v1/auth/login?return_to=${encodeURIComponent(returnTo)}`,
    ),
  },
}));

function renderConsole() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <EvaluationConsole />
    </QueryClientProvider>,
  );
}

describe("EvaluationConsole", () => {
  const mockedUseAuth = vi.mocked(useAuth);
  const mockedApi = vi.mocked(api);

  beforeEach(() => {
    vi.clearAllMocks();
    mockedApi.evaluation.mockResolvedValue({
      case_count: 15,
      baseline_root_cause_top1: 1,
      baseline_evidence_recall: 0.444,
      root_cause_top1: 1,
      showcase_top1: 1,
      causal_chain_coverage: 1,
      evidence_precision: 0.8,
      citation_validity: 1,
      evidence_recall: 1,
      unsupported_claim_rate: 0,
      action_accuracy: 1,
      forbidden_action_rate: 0,
      average_tool_calls: 4,
      average_cost_cny: 0,
      p95_latency_ms: 4,
    });
  });

  it("runs the regression suite with an enterprise admin session", async () => {
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

    expect(screen.queryByLabelText("管理员令牌")).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "运行 15 案例评测" }),
    );

    expect(mockedApi.evaluation).toHaveBeenCalledWith(undefined);
    expect(await screen.findByText("本次回归已完成")).toBeInTheDocument();
  });

  it("keeps the emergency admin token input when no admin session exists", () => {
    mockedUseAuth.mockReturnValue({
      session: {
        authenticated: false,
        sso_enabled: true,
        role: "guest",
        actor: null,
      },
      isLoading: false,
      error: null,
      logout: vi.fn(),
    });

    renderConsole();

    expect(screen.getByLabelText("管理员令牌")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "运行 15 案例评测" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("link", { name: "企业 SSO 登录" }),
    ).toBeInTheDocument();
  });
});
