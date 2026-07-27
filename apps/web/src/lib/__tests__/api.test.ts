import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";

function jsonResponse(value: unknown) {
  return {
    ok: true,
    json: vi.fn().mockResolvedValue(value),
  } as unknown as Response;
}

describe("api", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends the selected UTC window when creating an investigation", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        investigation_id: "inv-1",
        status: "queued",
        mode: "live",
        idempotent_replay: false,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.createInvestigation("case/1", "runner-token", "request-1", {
      startAt: "2026-01-10T09:00:00Z",
      endAt: "2026-01-10T10:00:00Z",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/investigations",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer runner-token",
          "Idempotency-Key": "request-1",
        }),
        body: JSON.stringify({
          incident_case_id: "case/1",
          mode: "live",
          start_at: "2026-01-10T09:00:00Z",
          end_at: "2026-01-10T10:00:00Z",
        }),
      }),
    );
  });

  it("uses the runner token when canceling an investigation", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: "canceled" }));
    vi.stubGlobal("fetch", fetchMock);

    await api.cancelInvestigation("inv/1", "runner-token");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/investigations/inv%2F1/cancel",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer runner-token",
        }),
      }),
    );
  });

  it("uploads an incident pack as multipart data without overriding its boundary", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: "imported-case" }));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["{}"], "incident.json", { type: "application/json" });

    await api.importIncident(file, "admin-token");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/incidents/import",
      expect.objectContaining({
        method: "POST",
        headers: { Authorization: "Bearer admin-token" },
        body: expect.any(FormData),
      }),
    );
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(init.headers).has("Content-Type")).toBe(false);
  });
});
