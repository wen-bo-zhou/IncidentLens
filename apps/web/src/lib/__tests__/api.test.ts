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

  it("uses an explicit credential when reading the private incident catalog", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]));
    vi.stubGlobal("fetch", fetchMock);

    await api.incidents("runner-token");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/incidents",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer runner-token",
        }),
      }),
    );
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

  it("protects investigation detail and issues a scoped stream ticket", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ investigation_id: "inv-1" }))
      .mockResolvedValueOnce(
        jsonResponse({
          ticket: "ticket with/slash",
          expires_at: "2026-07-27T12:05:00Z",
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await api.investigation("inv/1", "runner-token");
    await api.streamTicket("inv/1", "runner-token");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/v1/investigations/inv%2F1",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer runner-token",
        }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/v1/investigations/inv%2F1/stream-ticket",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer runner-token",
        }),
      }),
    );
    expect(api.eventsUrl("inv/1", "ticket with/slash")).toBe(
      "/api/v1/investigations/inv%2F1/events?ticket=ticket+with%2Fslash",
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

  it("sends operations filters and credentials when reading history", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ items: [], total: 0, limit: 20, offset: 0 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.investigationHistory("admin-token", {
      status: "failed",
      caseId: "case/1",
      limit: 20,
      offset: 40,
    });
    await api.auditEvents("admin-token", {
      action: "investigation.created",
      limit: 20,
      offset: 0,
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/v1/investigations?limit=20&offset=40&status=failed&case_id=case%2F1",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer admin-token",
        }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/v1/audit-events?limit=20&offset=0&action=investigation.created",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer admin-token",
        }),
      }),
    );
  });
});
