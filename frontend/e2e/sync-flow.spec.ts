import { expect, test } from "@playwright/test";

test("admin previews, confirms, and starts a manually selected sync", async ({ page }) => {
  let loggedIn = false;
  let previewed = false;
  const job = {
    id: "job-1", kind: "sync", state: "ready_to_confirm", created_at: "2026-07-14T00:00:00Z",
    request_snapshot: { user_id: "user-1", host_ids: ["host-1"], hosts: [{ id: "host-1", name: "lab-01", address: "192.0.2.10" }] },
    user_snapshot: { username: "alice" }, script_snapshot: null,
    targets: [{ host_id: "host-1", host_name: "lab-01", state: "succeeded", output: "预检完成", error: null, started_at: null, finished_at: null }],
  };

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/auth/me") return json(loggedIn ? { authenticated: true } : { detail: "请先登录" }, loggedIn ? 200 : 401);
    if (path === "/api/auth/login") { loggedIn = true; return route.fulfill({ status: 204 }); }
    if (path === "/api/auth/csrf") return json({ token: "csrf-token" });
    if (path === "/api/hosts") return json([{ id: "host-1", name: "lab-01", address: "192.0.2.10", port: 22, ssh_user: "ops", tags: ["lab"], status: "reachable" }]);
    if (path === "/api/users") return json([{ id: "user-1", username: "alice", display_name: "Alice", shell: "/bin/bash", home: "/home/alice", enabled: true }]);
    if (path === "/api/script-templates") return json([]);
    if (path === "/api/jobs") return json(previewed ? [job] : []);
    if (path === "/api/jobs/preview") { previewed = true; return json(job, 202); }
    if (path === "/api/jobs/job-1/execute") return json({ ...job, state: "running" }, 202);
    return json({ detail: `unexpected ${path}` }, 404);
  });

  await page.goto("/");
  await page.getByLabel("管理员密码").fill("correct-horse");
  await page.getByRole("button", { name: "进入控制台" }).click();
  await page.getByRole("button", { name: "用户与公钥" }).click();
  await page.getByRole("button", { name: "同步" }).click();
  await page.getByLabel(/lab-01/).check();
  await page.getByRole("button", { name: "执行预检" }).click();
  await expect(page.getByRole("button", { name: "确认并执行" })).toBeDisabled();
  await page.getByLabel("我已确认以上变更").check();
  await page.getByRole("button", { name: "确认并执行" }).click();
  await expect(page.locator(".job-detail .state-running")).toBeVisible();
});
