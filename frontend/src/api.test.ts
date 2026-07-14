import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "./api";

describe("api", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("does not label multipart credential uploads as JSON", async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ token: "csrf" }) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({}) });
    vi.stubGlobal("fetch", fetch);

    const form = new FormData();
    form.set("private_key_file", new File(["private-key"], "host.key"));
    form.set("sudo_password", "secret");
    await api("/hosts/host-1/credentials", { method: "PUT", body: form });

    expect(fetch.mock.calls[1][1].headers).not.toHaveProperty("Content-Type");
    expect(fetch.mock.calls[1][1].body).toBe(form);
  });
});
