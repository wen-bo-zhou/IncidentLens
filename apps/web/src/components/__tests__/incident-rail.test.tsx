import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { IncidentRail } from "@/components/incident-rail";

describe("IncidentRail", () => {
  it("unlocks the private catalog with a runner or admin credential", async () => {
    const user = userEvent.setup();
    const unlockCatalog = vi.fn().mockResolvedValue(undefined);
    render(
      <IncidentRail
        incidents={[]}
        onSelect={vi.fn()}
        loading={false}
        onUnlockCatalog={unlockCatalog}
      />,
    );

    await user.click(screen.getByRole("button", { name: "打开私有目录" }));
    await user.type(
      screen.getByLabelText("Runner / Admin 令牌"),
      "runner-token",
    );
    await user.click(screen.getByRole("button", { name: "加载私有事故" }));

    await waitFor(() =>
      expect(unlockCatalog).toHaveBeenCalledWith("runner-token"),
    );
    await waitFor(() =>
      expect(screen.queryByLabelText("Runner / Admin 令牌")).not.toBeInTheDocument(),
    );
  });

  it("submits a JSON incident pack with an explicit admin token", async () => {
    const user = userEvent.setup();
    const importIncident = vi.fn().mockResolvedValue(undefined);
    render(
      <IncidentRail
        incidents={[]}
        onSelect={vi.fn()}
        loading={false}
        onImportIncident={importIncident}
      />,
    );

    await user.click(screen.getByRole("button", { name: "导入事故包" }));
    const file = new File(["{}"], "incident.json", { type: "application/json" });
    await user.upload(screen.getByLabelText("JSON 事故包"), file);
    await user.type(screen.getByLabelText("管理员令牌"), "admin-token");
    await user.click(screen.getByRole("button", { name: "确认导入" }));

    await waitFor(() =>
      expect(importIncident).toHaveBeenCalledWith(file, "admin-token"),
    );
    await waitFor(() =>
      expect(screen.queryByLabelText("JSON 事故包")).not.toBeInTheDocument(),
    );
  });

  it("uses an enterprise runner session to refresh the private catalog", async () => {
    const user = userEvent.setup();
    const unlockCatalog = vi.fn().mockResolvedValue(undefined);
    render(
      <IncidentRail
        incidents={[]}
        onSelect={vi.fn()}
        loading={false}
        onUnlockCatalog={unlockCatalog}
        sessionRole="runner"
      />,
    );

    await user.click(
      screen.getByRole("button", { name: "刷新私有目录" }),
    );

    expect(unlockCatalog).toHaveBeenCalledWith("");
    expect(
      screen.queryByLabelText("Runner / Admin 令牌"),
    ).not.toBeInTheDocument();
  });

  it("uses an enterprise admin session to import without a token field", async () => {
    const user = userEvent.setup();
    const importIncident = vi.fn().mockResolvedValue(undefined);
    render(
      <IncidentRail
        incidents={[]}
        onSelect={vi.fn()}
        loading={false}
        onImportIncident={importIncident}
        sessionRole="admin"
      />,
    );

    await user.click(screen.getByRole("button", { name: "导入事故包" }));
    const file = new File(["{}"], "incident.json", {
      type: "application/json",
    });
    await user.upload(screen.getByLabelText("JSON 事故包"), file);
    expect(screen.queryByLabelText("管理员令牌")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确认导入" }));

    await waitFor(() =>
      expect(importIncident).toHaveBeenCalledWith(file, ""),
    );
  });
});
