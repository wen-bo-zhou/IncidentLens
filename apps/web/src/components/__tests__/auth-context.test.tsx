import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "@/components/auth-context";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  api: {
    session: vi.fn(),
    logout: vi.fn(),
    loginUrl: vi.fn((returnTo: string) => `/api/v1/auth/login?return_to=${returnTo}`),
  },
}));

function Probe() {
  const auth = useAuth();
  return (
    <div>
      <span>{auth.session?.actor ?? "guest"}</span>
      <span>{auth.session?.role ?? "loading"}</span>
      <button onClick={() => void auth.logout()}>退出</button>
    </div>
  );
}

function renderProvider() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe("AuthProvider", () => {
  const mockedApi = vi.mocked(api);

  beforeEach(() => {
    vi.clearAllMocks();
    mockedApi.session.mockResolvedValue({
      authenticated: true,
      sso_enabled: true,
      role: "admin",
      actor: "oidc-admin",
    });
    mockedApi.logout.mockResolvedValue(undefined);
  });

  it("loads the opaque server session without reading a browser token", async () => {
    renderProvider();

    expect(await screen.findByText("oidc-admin")).toBeInTheDocument();
    expect(screen.getByText("admin")).toBeInTheDocument();
    expect(mockedApi.session).toHaveBeenCalledOnce();
  });

  it("clears the local identity after the server revokes the session", async () => {
    const user = userEvent.setup();
    renderProvider();
    await screen.findByText("oidc-admin");

    await user.click(screen.getByRole("button", { name: "退出" }));

    expect(mockedApi.logout).toHaveBeenCalledOnce();
    expect(await screen.findAllByText("guest")).toHaveLength(2);
  });
});
