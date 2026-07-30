import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuth } from "@/components/auth-context";
import { SessionControl } from "@/components/session-control";

vi.mock("@/components/auth-context", () => ({
  useAuth: vi.fn(),
}));

describe("SessionControl", () => {
  const mockedUseAuth = vi.mocked(useAuth);

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("offers the enterprise login without placing credentials in the page", () => {
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

    render(<SessionControl returnTo="/operations" />);

    expect(
      screen.getByRole("link", { name: "企业 SSO 登录" }),
    ).toHaveAttribute(
      "href",
      "/api/v1/auth/login?return_to=%2Foperations",
    );
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("shows the current role and revokes the session on logout", async () => {
    const user = userEvent.setup();
    const logout = vi.fn().mockResolvedValue(undefined);
    mockedUseAuth.mockReturnValue({
      session: {
        authenticated: true,
        sso_enabled: true,
        role: "admin",
        actor: "oidc-admin",
      },
      isLoading: false,
      error: null,
      logout,
    });

    render(<SessionControl returnTo="/" />);
    await user.click(screen.getByRole("button", { name: "退出企业会话" }));

    expect(screen.getByText("ADMIN")).toBeInTheDocument();
    expect(screen.getByText("oidc-admin")).toBeInTheDocument();
    expect(logout).toHaveBeenCalledOnce();
  });
});
