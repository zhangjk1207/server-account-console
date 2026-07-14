# 主机凭证与用户运维 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让单管理员可持久化每台主机的 SSH 私钥和 sudo 密码，验证连接后管理已有本地用户、公钥及 SSH 密码登录。

**Architecture:** 在 SQLite 新增一对一的加密主机凭证记录，Fernet 主密钥由环境提供。所有连接由主机自己的临时私钥文件和 sudo 密码驱动；固定 Ansible playbook 负责盘点用户和受控变更，现有 Job/JobTarget/SSE 模型承载预检与执行。前端将机器页扩展为顶对齐的主机详情工作区。

**Tech Stack:** React、TypeScript、Vite、FastAPI、SQLAlchemy、Alembic、cryptography/Fernet、Ansible Runner、pytest、Vitest、Playwright。

## Global Constraints

- `CREDENTIAL_ENCRYPTION_KEY` 必须是 Fernet URL-safe base64 密钥；没有该密钥时拒绝保存或解密主机凭证。
- SSH 私钥只能经 multipart 文件上传，最大 64 KiB；拒绝带口令的私钥和无效私钥文本。
- 私钥、sudo 密码、一次性用户新密码不得进入 SQLite 明文、API 响应、日志、SSE、Job 快照、Ansible 事件或 Git。
- 主机指纹未确认或变化时，不得进行严格 SSH、sudo、用户盘点或任何变更。
- 仅允许固定操作：用户盘点、创建/编辑、锁定/解锁、重置密码、删除、组/Shell/家目录/到期时间、公钥、sudo 规则、SSH `PasswordAuthentication`。
- 用户删除、删除家目录、公钥移除或替换、密码重置和密码登录切换都必须预检和显式确认。
- 所有远程变更继续遵守单任务锁、逐机任务结果和 SSE 事件；读取用户可以立即执行但仍不得泄漏秘密。
- 所有 UI 文案、错误消息和文档使用简体中文；右侧工作区和机器详情从顶部对齐，登录页保留居中。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `backend/app/services/credentials.py` | Fernet 加密、凭证解密、私钥文件校验与临时文件生命周期 |
| `backend/app/services/host_connections.py` | 基于主机凭证的指纹扫描、SSH/sudo 测试和 Ansible 连接变量 |
| `backend/app/services/host_operations.py` | 固定用户盘点结果解析与主机操作 Job 创建/执行 |
| `backend/app/api/host_credentials.py` | multipart 凭证上传、状态与测试 API |
| `backend/app/api/host_operations.py` | 用户盘点、公钥管理、用户变更和 SSHD 预检/执行 API |
| `backend/app/schemas/credential.py` | 凭证状态和连接测试响应模型 |
| `backend/app/schemas/host_operation.py` | 用户盘点、操作预览、执行和 SSHD 状态模型 |
| `backend/ansible/host_operations.yml` | 固定主机运维 playbook |
| `backend/ansible/roles/host_operations/tasks/main.yml` | 用户事实、用户/公钥/sshd 受控任务 |
| `frontend/src/App.tsx` | 机器详情、凭证上传、用户运维和确认交互 |
| `frontend/src/api.ts` | 新增的主机凭证和操作类型/API 调用 |

### Task 1: 加密凭证持久化与迁移

**Files:**
- Create: `backend/app/services/credentials.py`, `backend/app/schemas/credential.py`, `backend/alembic/versions/003_host_credentials.py`, `backend/tests/services/test_credentials.py`, `backend/tests/api/test_host_credentials.py`
- Modify: `backend/app/core/config.py`, `backend/app/db/models.py`, `backend/app/main.py`, `backend/pyproject.toml`, `.env.example`, `compose.yml`

**Interfaces:**
- Produces `HostCredential` with ciphertext fields and non-secret verification metadata.
- Produces `CredentialCipher.encrypt(value: str) -> str`, `CredentialCipher.decrypt(token: str) -> str`, and `validate_private_key(data: bytes) -> str`.
- Requires `CREDENTIAL_ENCRYPTION_KEY`; raises `CredentialConfigurationError` when absent or invalid.

- [ ] **Step 1: Write the failing encryption and model tests**

```python
def test_credential_cipher_round_trip(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    cipher = CredentialCipher.from_settings()
    assert cipher.decrypt(cipher.encrypt("sudo-secret")) == "sudo-secret"

def test_private_key_validation_rejects_encrypted_key():
    with pytest.raises(ValueError, match="不支持带口令的私钥"):
        validate_private_key(b"-----BEGIN OPENSSH PRIVATE KEY-----\nencrypted private key\n")
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `cd backend && ../.venv/bin/pytest -q tests/services/test_credentials.py`

Expected: collection failure because `app.services.credentials` does not exist.

- [ ] **Step 3: Add configuration, model and Alembic migration**

```python
class HostCredential(TimestampedRecord, Base):
    __tablename__ = "host_credentials"
    __table_args__ = (UniqueConstraint("host_id", name="uq_host_credential_host"),)
    host_id: Mapped[str] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"), index=True)
    private_key_ciphertext: Mapped[str] = mapped_column(Text)
    sudo_password_ciphertext: Mapped[str] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ssh_verified: Mapped[bool | None] = mapped_column(Boolean)
    sudo_verified: Mapped[bool | None] = mapped_column(Boolean)
    last_error: Mapped[str | None] = mapped_column(Text)
```

Add `credential_encryption_key: str | None = None` to settings, direct `cryptography>=43` and `python-multipart>=0.0.9` dependencies, plus an empty `CREDENTIAL_ENCRYPTION_KEY=` entry in `.env.example` and Compose environment pass-through. The migration creates only ciphertext and metadata columns.

- [ ] **Step 4: Implement encryption and private-key validation**

```python
class CredentialCipher:
    @classmethod
    def from_settings(cls) -> "CredentialCipher":
        key = get_settings().credential_encryption_key
        if not key:
            raise CredentialConfigurationError("未配置凭证加密主密钥")
        return cls(Fernet(key.encode()))

def validate_private_key(data: bytes) -> str:
    if len(data) > 64 * 1024 or b"PRIVATE KEY" not in data:
        raise ValueError("私钥文件格式无效")
    if b"ENCRYPTED" in data or b"bcrypt" in data.lower():
        raise ValueError("不支持带口令的私钥")
    return data.decode("utf-8")
```

- [ ] **Step 5: Add status-only credential API tests and implementation**

```python
async def test_upload_never_returns_secret(client, csrf, private_key_file):
    response = await client.put(
        "/api/hosts/host-1/credentials",
        headers={"X-CSRF-Token": csrf},
        data={"sudo_password": "sudo-secret"},
        files={"private_key_file": ("id_ed25519", private_key_file, "application/octet-stream")},
    )
    assert response.status_code == 200
    assert response.json()["private_key_configured"] is True
    assert "sudo-secret" not in response.text
```

Implement `GET/PUT/DELETE /api/hosts/{id}/credentials`; use `UploadFile`, reject missing file/password, encrypt before `session.commit()`, and return `HostCredentialStatus` only.

- [ ] **Step 6: Run migration and focused tests**

Run: `cd backend && ../.venv/bin/alembic upgrade head && ../.venv/bin/pytest -q tests/services/test_credentials.py tests/api/test_host_credentials.py`

Expected: migration succeeds and all new tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend .env.example compose.yml
git commit -m "feat: persist encrypted host credentials"
```

### Task 2: 用每台主机凭证测试 SSH/sudo 并接入同步任务

**Files:**
- Create: `backend/app/services/host_connections.py`, `backend/tests/services/test_host_connections.py`
- Modify: `backend/app/api/hosts.py`, `backend/app/api/host_credentials.py`, `backend/app/services/hosts.py`, `backend/app/services/jobs.py`, `backend/app/services/runner.py`, `backend/tests/api/test_hosts.py`, `backend/tests/api/test_host_credentials.py`

**Interfaces:**
- Produces `CredentialProbeResult(fingerprint, requires_confirmation, ssh_ok, sudo_ok, error, latency_ms)`.
- Produces `test_host_credential(session, host) -> CredentialProbeResult` and `build_credential_inventory(host, credential, artifact) -> dict`.
- Produces `redact_connection_error(message: str) -> str`, which replaces the host sudo password and private-key path with `[REDACTED]`.
- Existing sync runner uses per-host credential files and `ansible_become_password`; it never uses a secret in `Job.request_snapshot`.

- [ ] **Step 1: Write failing probe tests**

```python
def test_unconfirmed_host_returns_fingerprint_without_attempting_login(monkeypatch, host, credential):
    monkeypatch.setattr(connections, "scan_host_key", lambda _: ("SHA256:new", "line", None))
    result = test_host_credential(session, host)
    assert result.requires_confirmation is True
    assert result.ssh_ok is None

def test_probe_checks_ssh_then_forced_sudo(monkeypatch, confirmed_host, credential):
    commands = []
    monkeypatch.setattr(connections.subprocess, "run", fake_run(commands, returns=[0, 0]))
    result = test_host_credential(session, confirmed_host)
    assert result.ssh_ok is True and result.sudo_ok is True
    assert any("-k" in command for command in commands)
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `cd backend && ../.venv/bin/pytest -q tests/services/test_host_connections.py`

Expected: import failure for `host_connections`.

- [ ] **Step 3: Implement strict credential probe and confirmation handoff**

```python
def test_host_credential(session: Session, host: Host) -> CredentialProbeResult:
    fingerprint, known_line, error = scan_host_key(host)
    if error:
        return CredentialProbeResult(None, False, False, None, error, None)
    if host.host_key_fingerprint != fingerprint:
        return CredentialProbeResult(fingerprint, True, None, None, None, None)
    with decrypted_key_file(session, host.id) as key_path, known_hosts_file(known_line) as known_hosts:
        ssh = run_strict_ssh(host, key_path, known_hosts, ["true"])
        sudo = run_strict_ssh(host, key_path, known_hosts, ["sudo", "-S", "-k", "-p", "", "true"], stdin=sudo_password)
    return CredentialProbeResult(fingerprint, False, ssh.ok, sudo.ok if ssh.ok else None, redact_connection_error(sudo.stderr or ssh.stderr), elapsed)
```

Update fingerprint confirmation to invoke this function after storing the exact scanned fingerprint. `POST /credentials/test` persists independent SSH and sudo outcomes. No current global-key probe may overwrite a credential probe result.

- [ ] **Step 4: Make Ansible inventory credential-aware and redact secrets**

```python
inventory_host = {
    "ansible_host": host.address,
    "ansible_user": host.ssh_user,
    "ansible_ssh_private_key_file": str(key_path),
    "ansible_ssh_common_args": strict_args,
    "ansible_become": True,
    "ansible_become_password": credential.sudo_password,
}
```

Write each decrypted key as a `0600` file beneath the job artifact; add all credential plaintext values to `RunnerRequest.sensitive_values`; replace those values recursively in every event before persistence. Delete key files in a `finally` block. Reject sync creation with a 422 when a selected host lacks a successfully verified credential.

- [ ] **Step 5: Run tests and static secret scan**

Run: `cd backend && ../.venv/bin/pytest -q tests/services/test_host_connections.py tests/services/test_runner.py tests/api/test_host_credentials.py tests/api/test_jobs.py && rg -n 'sudo-secret|BEGIN OPENSSH PRIVATE KEY' runtime backend/tests`

Expected: tests pass; `rg` has no secret match outside controlled fixture source.

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "feat: test per-host ssh and sudo credentials"
```

### Task 3: 固定 Ansible 用户盘点与主机操作任务

**Files:**
- Create: `backend/app/services/host_operations.py`, `backend/app/schemas/host_operation.py`, `backend/app/api/host_operations.py`, `backend/ansible/host_operations.yml`, `backend/ansible/roles/host_operations/tasks/main.yml`, `backend/tests/services/test_host_operations.py`, `backend/tests/api/test_host_operations.py`, `backend/tests/integration/test_host_operations_role.py`
- Modify: `backend/app/main.py`, `backend/app/services/jobs.py`, `backend/app/api/jobs.py`, `backend/app/db/models.py`, `backend/alembic/versions/004_host_operation_job_fields.py`

**Interfaces:**
- Produces `HostUserRead`, `HostUserOperationPreview`, `HostOperationExecute` and `SshPasswordAuthenticationRead` schemas.
- Produces `list_host_users(session, host) -> list[HostUserRead]`, `create_host_operation_preview(...) -> Job`, and `execute_host_operation(...) -> Job`.
- Uses `Job.kind` values `host_user_operation` and `ssh_password_authentication`; request snapshots never include a user new password.

- [ ] **Step 1: Write failing user inventory and operation-state tests**

```python
def test_parse_inventory_filters_system_users_and_never_exposes_shadow():
    users = parse_inventory({"getent_passwd": {"alice": ["x", "1001", "1001", "", "/home/alice", "/bin/bash"]}})
    assert users == [HostUserRead(username="alice", uid=1001, primary_group="1001", groups=[], shell="/bin/bash", home="/home/alice", locked=None, expires_at=None)]

def test_preview_snapshot_excludes_one_time_password(session, host):
    job = create_host_operation_preview(session, host, HostUserOperation(action="reset_password", username="alice"))
    assert "new_password" not in json.dumps(job.request_snapshot)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd backend && ../.venv/bin/pytest -q tests/services/test_host_operations.py tests/api/test_host_operations.py`

Expected: collection failure because operation schemas and service do not exist.

- [ ] **Step 3: Implement read-only inventory playbook and parser**

```yaml
- name: Load local user and group facts
  ansible.builtin.getent:
    database: "{{ item }}"
  loop: [passwd, group]

- name: Emit non-system local users as JSON
  ansible.builtin.debug:
    msg: "{{ host_users | to_json }}"
```

The role builds user data from passwd/group only, filters UID >= 1000, reads account lock/expiry through fixed `passwd -S` and `chage -l` commands with `no_log: true` where necessary, and never requests `shadow`. Parse only the structured debug payload; reject malformed results.

- [ ] **Step 4: Implement fixed preview/execute operations**

```python
class HostUserOperation(BaseModel):
    action: Literal["upsert", "lock", "unlock", "reset_password", "delete", "keys"]
    username: str
    remove_home: bool = False
    managed_user_id: str | None = None
    public_keys: list[str] = []
    key_mode: Literal["append", "remove", "replace"] | None = None

class HostOperationExecute(BaseModel):
    new_password: SecretStr | None = None
```

Create preview Jobs with operation fields excluding `new_password`; require `new_password` only when executing reset-password. The runner passes it as a sensitive extra var to a `no_log` task and discards it after execution. Validate that `managed_user_id` expands to the existing desired user and active public keys.

- [ ] **Step 5: Implement the Ansible fixed action matrix**

```yaml
- name: Apply user state
  ansible.builtin.user:
    name: "{{ operation.username }}"
    state: "{{ 'absent' if operation.action == 'delete' else 'present' }}"
    remove: "{{ operation.remove_home | default(false) }}"
    password_lock: "{{ operation.action == 'lock' }}"
  when: operation.action in ['upsert', 'lock', 'unlock', 'delete']

- name: Set one-time password
  ansible.builtin.command:
    cmd: chpasswd
    stdin: "{{ host_operation_new_password }}"
  no_log: true
  when: operation.action == 'reset_password'
```

Use `ansible.posix.authorized_key` for append/remove/replace, only after explicit API confirmation. Keep operations literal-dispatched; never interpolate a user command string.

- [ ] **Step 6: Run API and role tests**

Run: `cd backend && ../.venv/bin/pytest -q tests/services/test_host_operations.py tests/api/test_host_operations.py tests/integration/test_host_operations_role.py`

Expected: all tests pass and tests assert public keys may be listed but new passwords are absent from job/events.

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat: add fixed host user operations"
```

### Task 4: SSH 密码登录状态、预检与执行

**Files:**
- Create: `backend/ansible/roles/host_operations/tasks/sshd.yml`
- Modify: `backend/app/services/host_operations.py`, `backend/app/api/host_operations.py`, `backend/app/schemas/host_operation.py`, `backend/ansible/roles/host_operations/tasks/main.yml`, `backend/tests/services/test_host_operations.py`, `backend/tests/api/test_host_operations.py`, `backend/tests/integration/test_host_operations_role.py`

**Interfaces:**
- Produces `get_ssh_password_authentication(session, host) -> SshPasswordAuthenticationRead`.
- Accepts `SshPasswordAuthenticationPreview(enabled: bool)` and creates a `ssh_password_authentication` preview Job.

- [ ] **Step 1: Write failing SSHD operation tests**

```python
def test_password_authentication_preview_requires_verified_sudo_host(client, host_without_sudo):
    response = client.post(f"/api/hosts/{host_without_sudo.id}/ssh-password-authentication/preview", json={"enabled": False})
    assert response.status_code == 422

def test_sshd_role_validates_before_replacing_fragment(role_text):
    assert "sshd -t" in role_text
    assert "99-server-account-console.conf" in role_text
    assert role_text.index("sshd -t") < role_text.index("reload")
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd backend && ../.venv/bin/pytest -q tests/api/test_host_operations.py tests/integration/test_host_operations_role.py`

Expected: failure because SSHD schemas/routes/tasks do not exist.

- [ ] **Step 3: Implement SSHD status and role**

```yaml
- name: Validate candidate sshd configuration
  ansible.builtin.command:
    cmd: "sshd -t -f {{ candidate_sshd_config }}"
  changed_when: false

- name: Atomically install managed password-authentication fragment
  ansible.builtin.copy:
    content: "PasswordAuthentication {{ 'yes' if operation.enabled else 'no' }}\n"
    dest: /etc/ssh/sshd_config.d/99-server-account-console.conf
    mode: "0644"
  notify: Reload SSH service
```

Build candidate configuration by copying the existing managed fragment to a temporary path, validate before replacing the managed fragment, and use handlers that try `sshd` then `ssh`. The read path runs `sshd -T` and parses only `passwordauthentication yes|no`.

- [ ] **Step 4: Enforce confirmation and run focused tests**

```python
if job.kind == "ssh_password_authentication" and job.state != "ready_to_confirm":
    raise JobStateError("只有预检完成的 SSH 登录策略任务可以执行")
```

Run: `cd backend && ../.venv/bin/pytest -q tests/api/test_host_operations.py tests/services/test_host_operations.py tests/integration/test_host_operations_role.py`

Expected: SSHD status, preflight gate and validation-order tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat: manage ssh password authentication"
```

### Task 5: 顶对齐的机器详情与受控运维 UI

**Files:**
- Modify: `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/styles.css`, `frontend/src/App.test.tsx`, `frontend/e2e/sync-flow.spec.ts`, `frontend/package.json`

**Interfaces:**
- `Host` exposes credential status; `api.ts` defines `HostCredentialStatus`, `HostUser`, `HostUserOperation`, `SshPasswordAuthentication`.
- Machine table action opens `HostDetail`; secrets are sent via `FormData`, then cleared from React state.

- [ ] **Step 1: Write failing component tests**

```tsx
it("uploads a key file and clears sensitive fields after saving", async () => {
  render(<App />);
  await openHostDetail();
  fireEvent.change(screen.getByLabelText("SSH 私钥文件"), { target: { files: [new File(["key"], "id_ed25519")] } });
  fireEvent.change(screen.getByLabelText("sudo 密码"), { target: { value: "sudo-secret" } });
  fireEvent.click(screen.getByRole("button", { name: "保存凭证" }));
  await waitFor(() => expect(mockedFetch).toHaveBeenCalledWith(expect.stringContaining("/credentials"), expect.anything()));
  expect(screen.getByLabelText("sudo 密码")).toHaveValue("");
});

it("places the workspace at the top of the application shell", () => {
  render(<App />);
  expect(screen.getByRole("main")).toHaveClass("workspace");
});
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd frontend && npm test -- --run src/App.test.tsx`

Expected: failure because no machine-detail credential controls exist.

- [ ] **Step 3: Implement credential and verification controls**

```tsx
const body = new FormData();
body.set("private_key_file", file);
body.set("sudo_password", sudoPassword);
await api<HostCredentialStatus>(`/hosts/${host.id}/credentials`, { method: "PUT", body });
setPrivateKeyFile(null);
setSudoPassword("");
```

Update `api()` so multipart requests do not set `Content-Type`; retain CSRF. Display only credential state, masked errors, last test time, and independent SSH/sudo badges. Use the fingerprint-confirmation flow when the test asks for confirmation.

- [ ] **Step 4: Implement user inventory and dangerous-operation confirmation**

```tsx
const [confirmDangerous, setConfirmDangerous] = useState(false);
const requiresConfirmation = ["reset_password", "delete", "keys"].includes(operation.action);
<Button disabled={requiresConfirmation && !confirmDangerous}>执行确认的变更</Button>
```

Build a dense top-aligned machine detail view with user filter, managed-person selector, public-key append/remove/replace, lock/unlock, reset password, delete/remove-home controls, SSH password-login preview and explicit confirmation. Never display private key, sudo password or new user password after submission.

- [ ] **Step 5: Correct shell alignment and responsive layout**

```css
.layout { align-items: start; }
.workspace { align-self: start; margin: 0; min-height: 100vh; }
.host-detail { align-items: start; }
.login { place-items: center; }
```

Use stable grid areas rather than vertical centering. On mobile, stack machine detail blocks in the same sequence without overlap.

- [ ] **Step 6: Add browser flow and run frontend verification**

```ts
test("admin uploads a credential, verifies sudo, inspects users, and previews password login", async ({ page }) => {
  await page.setInputFiles('input[aria-label="SSH 私钥文件"]', { name: "id_ed25519", mimeType: "text/plain", buffer: Buffer.from("key") });
  await page.getByLabel("sudo 密码").fill("sudo-secret");
  await page.getByRole("button", { name: "保存凭证" }).click();
  await expect(page.getByText("sudo 已验证")).toBeVisible();
});
```

Run: `cd frontend && npm test -- --run && npm run build && npx playwright test`

Expected: all component tests, production build and browser tests pass.

- [ ] **Step 7: Commit**

```bash
git add frontend
git commit -m "feat: add host credential operations UI"
```

### Task 6: 发布配置、端到端验收与文档

**Files:**
- Modify: `.env.example`, `compose.yml`, `README.md`, `docs/deployment.md`, `docs/operations.md`, `docs/release-checklist.md`, `backend/tests/api/test_health.py`

**Interfaces:**
- Health endpoint includes `credential_encryption` as `ok` only when the Fernet key is configured and valid.

- [ ] **Step 1: Write failing health and documentation assertions**

```python
def test_health_is_degraded_without_credential_encryption_key(monkeypatch):
    monkeypatch.delenv("CREDENTIAL_ENCRYPTION_KEY", raising=False)
    response = client.get("/api/health")
    assert response.json()["checks"]["credential_encryption"] == "degraded"
```

- [ ] **Step 2: Implement health check and update deployment guidance**

Document Fernet key generation:

```sh
.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Document permissions for runtime SQLite and temporary artifacts, the no-passphrase private-key limitation, credential replacement, safe password-login rollback and restore testing.

- [ ] **Step 3: Run complete backend and deployment verification**

Run:

```sh
cd backend && ../.venv/bin/pytest -q --cache-clear
../.venv/bin/ansible-playbook --syntax-check -i 'localhost,' -c local ansible/playbook.yml
../.venv/bin/ansible-playbook --syntax-check -i 'localhost,' -c local ansible/host_operations.yml
cd .. && DATABASE_URL=sqlite:////tmp/compose-check.db CONTROL_SSH_KEY_PATH=/run/secrets/key SSH_KEY_PATH=/tmp/key ADMIN_PASSWORD_HASH=placeholder SESSION_SECRET=placeholder CREDENTIAL_ENCRYPTION_KEY=placeholder APP_ORIGIN=http://localhost:8080 docker compose config
```

Expected: all tests and both playbook syntax checks pass; Compose expands successfully.

- [ ] **Step 4: Commit and push**

```bash
git add .env.example compose.yml README.md docs backend
git commit -m "docs: document encrypted host operations"
git push origin main
```

## Plan Self-Review

- Spec coverage: Task 1 implements encrypted persistent upload storage; Task 2 implements SSH/sudo testing and credential-backed sync; Tasks 3-4 implement existing-user/public-key and password-login functionality; Task 5 implements the requested UI and top alignment; Task 6 covers deployment and acceptance.
- Placeholder scan: no `TODO`, `TBD`, “implement later”, or unnamed interfaces remain.
- Type consistency: `HostCredentialStatus`, `CredentialProbeResult`, `HostUserOperation`, `HostOperationExecute` and the `Job.kind` values are introduced before they are consumed by later tasks.
