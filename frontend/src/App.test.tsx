import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { api } from "./api";

vi.mock("./api", () => ({
  api: vi.fn(),
  login: vi.fn(),
}));

const mockedApi = vi.mocked(api);

describe("App", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
    let credentialSaved = false;
    mockedApi.mockImplementation((path: string, init?: RequestInit) => {
      if (path === "/hosts") return Promise.resolve([{ id: "host-1", name: "lab-01", address: "192.0.2.10", port: 22, ssh_user: "ops", tags: [], status: "reachable" }]);
      if (path === "/users" && init?.method === "POST") return Promise.resolve({ id: "user-2", username: "bob", display_name: "Bob", shell: "/bin/bash", home: "/home/bob", enabled: true });
      if (path === "/users") return Promise.resolve([{ id: "user-1", username: "alice", display_name: "Alice", shell: "/bin/bash", home: "/home/alice", enabled: true }]);
      if (path === "/users/user-1/keys") return Promise.resolve([{ id: "key-1", managed_user_id: "user-1", public_key: "ssh-ed25519 AAAA test", fingerprint: "SHA256:known-key", comment: "alice@laptop", enabled: true }]);
      if (path === "/users/user-1/host-states") return Promise.resolve([{ host_id: "host-1", host_name: "lab-01", status: "synced", synced_at: "2026-07-14T00:00:00Z", desired_hash: "abc" }]);
      if (path === "/users/user-1" && init?.method === "DELETE") return Promise.resolve(undefined);
      if (path === "/hosts/host-1" && init?.method === "DELETE") return Promise.resolve(undefined);
      if (path === "/hosts/host-1/credentials" && (!init?.method || init.method === "GET")) return Promise.resolve({ private_key_configured: credentialSaved, sudo_password_configured: credentialSaved, verified_at: null, ssh_verified: credentialSaved || null, sudo_verified: credentialSaved || null, last_error: null });
      if (path === "/hosts/host-1/credentials" && init?.method === "PUT") { credentialSaved = true; return Promise.resolve({ private_key_configured: true, sudo_password_configured: true, verified_at: null, ssh_verified: null, sudo_verified: null, last_error: null }); }
      if (path === "/hosts/host-1/credentials/test") return Promise.resolve({ fingerprint: "SHA256:host", requires_confirmation: false, ssh_ok: true, sudo_ok: true, error: null, latency_ms: 12 });
      if (path === "/hosts/host-1/users") return Promise.resolve([{ username: "bob", uid: 1001, primary_group: "bob", groups: ["bob", "docker"], shell: "/bin/bash", home: "/home/bob", locked: false, expires_at: null, public_keys: [] }]);
      if (path === "/hosts/host-1/ssh-password-authentication") return Promise.resolve({ enabled: false });
      if (path === "/hosts/host-1/user-operations/preview") return Promise.resolve({ id: "job-2", state: "ready_to_confirm", kind: "host_user_operation", created_at: "2026-07-14T00:00:00Z", request_snapshot: JSON.parse(String(init?.body)), targets: [] });
      if (path === "/host-operations/job-2/execute") return Promise.resolve({ id: "job-2", state: "running", kind: "host_user_operation", created_at: "2026-07-14T00:00:00Z", request_snapshot: {}, targets: [] });
      if (path === "/script-templates") return Promise.resolve([{ id: "script-1", name: "prepare-home", description: "创建目录", version: 2, enabled: true, body: "mkdir -p /srv/alice" }]);
      if (path === "/script-templates/script-1" && init?.method === "DELETE") return Promise.resolve(undefined);
      if (path === "/jobs") return Promise.resolve([]);
      if (path === "/jobs/preview") return Promise.resolve({ id: "job-1", state: "ready_to_confirm", kind: "sync", created_at: "2026-07-14T00:00:00Z", request_snapshot: JSON.parse(String(init?.body)) });
      if (path === "/jobs/job-1/execute") return Promise.resolve({ id: "job-1", state: "running", kind: "sync", created_at: "2026-07-14T00:00:00Z", request_snapshot: {} });
      throw new Error(`Unexpected request: ${path}`);
    });
  });

  it("sends the selected post-script template with a manual preview", async () => {
    render(<App />);
    await screen.findByRole("button", { name: "用户与公钥" });
    fireEvent.click(screen.getByRole("button", { name: "用户与公钥" }));
    await screen.findByText("alice");
    fireEvent.click(screen.getByRole("button", { name: /同步/ }));
    fireEvent.click(screen.getByLabelText(/lab-01/));
    fireEvent.change(screen.getByLabelText("后置脚本"), { target: { value: "script-1" } });
    fireEvent.click(screen.getByRole("button", { name: "执行预检" }));

    await waitFor(() => expect(mockedApi).toHaveBeenCalledWith("/jobs/preview", expect.objectContaining({
      body: JSON.stringify({ user_id: "user-1", host_ids: ["host-1"], script_template_id: "script-1" }),
    })));
  });

  it("requires explicit confirmation after preview before execution", async () => {
    render(<App />);
    await screen.findByRole("button", { name: "用户与公钥" });
    fireEvent.click(screen.getByRole("button", { name: "用户与公钥" }));
    await screen.findByText("alice");
    fireEvent.click(screen.getByRole("button", { name: /同步/ }));
    fireEvent.click(screen.getByLabelText(/lab-01/));
    fireEvent.click(screen.getByRole("button", { name: "执行预检" }));

    const execute = await screen.findByRole("button", { name: "确认并执行" });
    expect((execute as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText("我已确认以上变更"));
    expect((execute as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(execute);

    await waitFor(() => expect(mockedApi).toHaveBeenCalledWith("/jobs/job-1/execute", expect.objectContaining({ method: "POST" })));
  });

  it("shows existing SSH keys before adding another key", async () => {
    render(<App />);
    await screen.findByRole("button", { name: "用户与公钥" });
    fireEvent.click(screen.getByRole("button", { name: "用户与公钥" }));
    await screen.findByText("alice");
    fireEvent.click(screen.getByRole("button", { name: "公钥" }));

    expect(await screen.findByText("SHA256:known-key")).toBeTruthy();
    expect(screen.getByText("alice@laptop")).toBeTruthy();
    expect(await screen.findByText("lab-01")).toBeTruthy();
  });

  it("sends directory and symlink declarations when creating a user", async () => {
    render(<App />);
    await screen.findByRole("button", { name: "用户与公钥" });
    fireEvent.click(screen.getByRole("button", { name: "用户与公钥" }));
    fireEvent.change(screen.getByLabelText("用户名"), { target: { value: "bob" } });
    fireEvent.change(screen.getByLabelText("显示名"), { target: { value: "Bob" } });
    fireEvent.change(screen.getByLabelText("目录配置"), { target: { value: '[{"path":"/srv/bob","mode":"0750"}]' } });
    fireEvent.change(screen.getByLabelText("软链接配置"), { target: { value: '[{"path":"/home/bob/work","target":"/srv/bob"}]' } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => {
      const call = mockedApi.mock.calls.find(([path, init]) => path === "/users" && init?.method === "POST");
      expect(call).toBeTruthy();
      expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ username: "bob", directories: [{ path: "/srv/bob", mode: "0750" }], symlinks: [{ path: "/home/bob/work", target: "/srv/bob" }] });
    });
  });

  it("offers confirmed archival and disable actions for managed records", async () => {
    vi.stubGlobal("confirm", vi.fn(() => true));
    render(<App />);
    await screen.findByRole("button", { name: "机器" });
    fireEvent.click(screen.getByRole("button", { name: "机器" }));
    fireEvent.click(await screen.findByRole("button", { name: "归档" }));
    await waitFor(() => expect(mockedApi).toHaveBeenCalledWith("/hosts/host-1", expect.objectContaining({ method: "DELETE" })));

    fireEvent.click(screen.getByRole("button", { name: "用户与公钥" }));
    fireEvent.click(await screen.findByRole("button", { name: "停用用户" }));
    await waitFor(() => expect(mockedApi).toHaveBeenCalledWith("/users/user-1", expect.objectContaining({ method: "DELETE" })));

    fireEvent.click(screen.getByRole("button", { name: "脚本模板" }));
    fireEvent.click(await screen.findByRole("button", { name: "停用模板" }));
    await waitFor(() => expect(mockedApi).toHaveBeenCalledWith("/script-templates/script-1", expect.objectContaining({ method: "DELETE" })));
  });

  it("uploads per-host credentials and previews a fixed host user operation", async () => {
    render(<App />);
    await screen.findByRole("button", { name: "机器" });
    fireEvent.click(screen.getByRole("button", { name: "机器" }));
    fireEvent.click(await screen.findByRole("button", { name: "详情" }));

    expect(await screen.findByRole("heading", { name: "lab-01" })).toBeTruthy();
    const key = new File(["-----BEGIN OPENSSH PRIVATE KEY-----\nkey\n-----END OPENSSH PRIVATE KEY-----"], "lab-01.key", { type: "application/octet-stream" });
    fireEvent.change(screen.getByLabelText("SSH 私钥文件"), { target: { files: [key] } });
    fireEvent.change(screen.getByLabelText("sudo 密码"), { target: { value: "sudo-secret" } });
    fireEvent.click(screen.getByRole("button", { name: "保存凭证" }));

    await waitFor(() => {
      const call = mockedApi.mock.calls.find(([path, init]) => path === "/hosts/host-1/credentials" && init?.method === "PUT");
      expect(call?.[1]?.body).toBeInstanceOf(FormData);
      expect((call?.[1]?.body as FormData).get("private_key_file")).toBe(key);
      expect((call?.[1]?.body as FormData).get("sudo_password")).toBe("sudo-secret");
    });

    fireEvent.click(screen.getByRole("button", { name: "测试 SSH 与 sudo" }));
    await waitFor(() => expect(mockedApi).toHaveBeenCalledWith("/hosts/host-1/credentials/test", expect.objectContaining({ method: "POST" })));
    fireEvent.click(screen.getByRole("button", { name: "关闭详情" }));
    fireEvent.click(screen.getByRole("button", { name: "详情" }));
    expect(await screen.findByText("SSH：通过")).toBeTruthy();
    expect(screen.getByText("sudo：通过")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "盘点已有用户" }));
    expect(await screen.findByText(/bob, docker/)).toBeTruthy();

    fireEvent.change(screen.getByLabelText("运维动作"), { target: { value: "lock" } });
    fireEvent.change(screen.getByLabelText("目标用户名"), { target: { value: "bob" } });
    fireEvent.click(screen.getByRole("button", { name: "预检用户操作" }));
    await waitFor(() => expect(mockedApi).toHaveBeenCalledWith("/hosts/host-1/user-operations/preview", expect.objectContaining({
      method: "POST", body: JSON.stringify({ action: "lock", username: "bob" }),
    })));
    fireEvent.click(await screen.findByLabelText("我已确认以上变更"));
    fireEvent.click(screen.getByRole("button", { name: "确认并执行" }));
    await waitFor(() => expect(mockedApi).toHaveBeenCalledWith("/host-operations/job-2/execute", expect.objectContaining({ method: "POST", body: "{}" })));
  });
});
