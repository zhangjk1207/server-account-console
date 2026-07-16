import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { api } from "./api";

vi.mock("./api", () => ({ api: vi.fn(), login: vi.fn() }));
const mockedApi = vi.mocked(api);

describe("member provisioning workbench", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
    mockedApi.mockImplementation((path: string, init?: RequestInit) => {
      if (path === "/hosts") return Promise.resolve([{ id: "host-1", name: "gpu-a100-01", address: "192.0.2.10", port: 22, ssh_user: "ops", tags: ["a100"], data_root: "/mnt/train", status: "reachable" }]);
      if (path === "/users") return Promise.resolve([{ id: "user-1", username: "alice", display_name: "Alice", shell: "/bin/bash", home: "/home/alice", enabled: true }]);
      if (path === "/permission-templates") return Promise.resolve([{ id: "tpl-1", name: "Docker training", description: "", groups: ["docker"], sudo_rule: null, enabled: true }]);
      if (path === "/hosts/host-1/credentials" && init?.method === "PUT") return Promise.resolve({ private_key_configured:true, sudo_password_configured:true, ssh_verified:null, sudo_verified:null, verified_at:null, last_error:null });
      if (path === "/jobs") return Promise.resolve([]);
      if (path === "/users/user-1/keys") return Promise.resolve([{ id: "key-1", managed_user_id: "user-1", public_key: "ssh-ed25519 AAAA test", fingerprint: "SHA256:key", comment: "alice", enabled: true }]);
      if (path === "/users/user-1/access-grants") return Promise.resolve([]);
      if (path === "/users/user-1/access-grants/preview") return Promise.resolve({ id: "job-1", state: "ready_to_confirm", kind: "access_grant_provision", created_at: "2026-07-16T00:00:00Z", request_snapshot: { grants: [] }, targets: [] });
      if (path === "/access-grant-jobs/job-1/execute") return Promise.resolve({ id: "job-1", state: "running", kind: "access_grant_provision", created_at: "2026-07-16T00:00:00Z", request_snapshot: {}, targets: [] });
      throw new Error(`Unexpected request: ${path}`);
    });
  });

  it("submits selected machines with independent usernames and no client data path", async () => {
    render(<App />);
    await screen.findByRole("heading", { name:"Alice" });
    await screen.findByText("SSH 公钥");
    fireEvent.click(await screen.findByLabelText("选择 gpu-a100-01"));
    fireEvent.change(screen.getByLabelText("gpu-a100-01 用户名"), { target: { value: "alice-gpu" } });
    fireEvent.click(screen.getByRole("button", { name: "预检开通" }));

    await waitFor(() => {
      const call = mockedApi.mock.calls.find(([path]) => path === "/users/user-1/access-grants/preview");
      expect(call).toBeTruthy();
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({ grants: [{ host_id: "host-1", username: "alice-gpu", permission_template_id: "tpl-1", groups_override: null, sudo_rule_override: null }] });
    });
  });

  it("requires confirmation before running a prepared access batch", async () => {
    render(<App />);
    await screen.findByRole("heading", { name:"Alice" });
    fireEvent.click(await screen.findByLabelText("选择 gpu-a100-01"));
    fireEvent.click(screen.getByRole("button", { name: "预检开通" }));
    const execute = await screen.findByRole("button", { name: "确认并开通" });
    expect((execute as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText("我已核对本批次变更"));
    fireEvent.click(execute);
    await waitFor(() => expect(mockedApi).toHaveBeenCalledWith("/access-grant-jobs/job-1/execute", expect.objectContaining({ method: "POST" })));
  });

  it("keeps the per-machine management credential in machine settings", async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name:"机器" }));
    fireEvent.click(screen.getByText("连接设置"));
    const privateKey = new File(["private"], "gpu-a100-01.key", { type:"application/octet-stream" });
    fireEvent.change(screen.getByLabelText("gpu-a100-01 管理私钥"), { target:{ files:[privateKey] } });
    fireEvent.change(screen.getByLabelText("gpu-a100-01 sudo 密码"), { target:{ value:"secret" } });
    fireEvent.click(screen.getByRole("button", { name:"保存连接凭据" }));
    await waitFor(() => {
      const call = mockedApi.mock.calls.find(([path, init]) => path === "/hosts/host-1/credentials" && init?.method === "PUT");
      expect(call?.[1]?.body).toBeInstanceOf(FormData);
      expect((call?.[1]?.body as FormData).get("private_key_file")).toBe(privateKey);
    });
  });
});
