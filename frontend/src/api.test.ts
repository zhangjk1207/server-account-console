import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "./api";

describe("api", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("obtains a CSRF token before the first authenticated mutation", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ token: "csrf-token" }) })
      .mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({ id: "host-1" }) });
    vi.stubGlobal("fetch", fetchMock);

    await api<{ id: string }>("/hosts", { method: "POST", body: "{}" });

    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/auth/csrf", expect.objectContaining({ credentials: "include" }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/hosts", expect.objectContaining({
      headers: expect.objectContaining({ "X-CSRF-Token": "csrf-token" }),
    }));
  });
});
