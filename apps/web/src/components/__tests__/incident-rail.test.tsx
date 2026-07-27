import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { IncidentRail } from "@/components/incident-rail";

describe("IncidentRail", () => {
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
});
