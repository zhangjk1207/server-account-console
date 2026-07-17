import { expect, test } from "@playwright/test";

test("admin previews and confirms a member-centric access grant", async ({ page }) => {
  let loggedIn = false;
  const job = { id:"job-1", kind:"access_grant_provision", state:"ready_to_confirm", created_at:"2026-07-16T00:00:00Z", request_snapshot:{ grants:[{ host_id:"host-1", username:"alice-gpu", account_origin:"created", data_directory:"/mnt/train/alice-gpu", command_preview:{ label:"等价命令，实际由 Ansible 模块执行", tasks:["创建账号和数据目录"], commands:["useradd -M alice-gpu", "ln -s /mnt/train/alice-gpu /home/alice-gpu"], warnings:[], key_fingerprints:["SHA256:key"] } }] }, targets:[{ host_id:"host-1", host_name:"gpu-a100-01", state:"succeeded", output:"", error:null, started_at:null, finished_at:null }] };
  await page.route("**/api/**", async (route) => {
    const request = route.request(); const path = new URL(request.url()).pathname;
    const json = (body:unknown, status = 200) => route.fulfill({ status, contentType:"application/json", body:JSON.stringify(body) });
    if (path === "/api/auth/me") return json(loggedIn ? { authenticated:true } : { detail:"请先登录" }, loggedIn ? 200 : 401);
    if (path === "/api/auth/login") { loggedIn = true; return route.fulfill({ status:204 }); }
    if (path === "/api/auth/csrf") return json({ token:"csrf-token" });
    if (path === "/api/hosts") return json([{ id:"host-1", name:"gpu-a100-01", address:"192.0.2.10", port:22, ssh_user:"ops", tags:["a100"], data_root:"/mnt/train", status:"reachable" }]);
    if (path === "/api/users") return json([{ id:"user-1", username:"alice", display_name:"Alice", shell:"/bin/bash", home:"/home/alice", enabled:true }]);
    if (path === "/api/permission-templates") return json([{ id:"tpl-1", name:"Docker training", description:"", groups:["docker"], sudo_rule:null, enabled:true }]);
    if (path === "/api/jobs") return json([]);
    if (path === "/api/users/user-1/keys") return json([{ id:"key-1", managed_user_id:"user-1", public_key:"ssh-ed25519 AAAA", fingerprint:"SHA256:key", comment:"alice", enabled:true }]);
    if (path === "/api/users/user-1/access-grants") return json([]);
    if (path === "/api/users/user-1/access-grants/preview") return json(job, 202);
    if (path === "/api/access-grant-jobs/job-1/execute") return json({ ...job, state:"running" }, 202);
    return json({ detail:`unexpected ${path}` }, 404);
  });

  await page.goto("/");
  await page.getByLabel("管理员密码").fill("correct-horse");
  await page.getByRole("button", { name:"进入控制台" }).click();
  await page.getByLabel("选择 gpu-a100-01").check();
  await page.getByLabel("gpu-a100-01 用户名").fill("alice-gpu");
  await page.getByRole("button", { name:"预检开通" }).click();
  await expect(page.getByText("useradd -M alice-gpu")).toBeVisible();
  await expect(page.getByRole("button", { name:"确认并开通" })).toBeDisabled();
  await page.getByLabel("我已审阅以上命令").check();
  await page.screenshot({ path:"/tmp/server-account-console-member-flow.png", fullPage:true });
  await page.setViewportSize({ width:390, height:844 });
  await expect(page.getByText("useradd -M alice-gpu")).toBeVisible();
  await expect(page.getByRole("button", { name:"确认并开通" })).toBeVisible();
  await page.screenshot({ path:"/tmp/server-account-console-member-flow-mobile.png", fullPage:true });
  await page.getByRole("button", { name:"确认并开通" }).click();
  await expect(page.getByText("执行中")).toBeVisible();
});
