# Server Account Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-hosted, single-administrator web console that previews and applies Linux account, SSH key, permission, symlink, and controlled post-script changes to manually selected hosts.

**Architecture:** A React + shadcn/ui Vite frontend calls a FastAPI JSON API. FastAPI stores desired state and immutable task snapshots in SQLite, runs a fixed Ansible role through Ansible Runner, persists per-host events, and streams job output over SSE. The deployment is one internal Docker Compose stack; the control SSH private key is a read-only mounted secret.

**Tech Stack:** React, TypeScript, Vite, shadcn/ui, TanStack Query, FastAPI, SQLAlchemy 2, Alembic, SQLite, Pydantic, Ansible Runner, pytest, Playwright, Docker Compose.

## Global Constraints

- UI copy, validation messages, and deployment documentation are Simplified Chinese.
- The application is single-administrator and internal-network only; no RBAC, SSO, approvals, scheduling, arbitrary terminal, password rotation, or cloud inventory belongs in this implementation.
- A host is never a target until SSH connectivity and its host-key fingerprint have been explicitly confirmed.
- The control SSH private key is supplied only by a read-only mount or Docker secret, never stored in SQLite, API responses, snapshots, logs, or Git.
- Only one preview or execution task may run globally at a time; runner concurrency is five hosts and host timeout is five minutes.
- A preview expires after 30 minutes. Only a `ready_to_confirm` preview can start an execution.
- The fixed role preserves existing unmanaged `authorized_keys`; removal of a key or user is out of scope.
- Each code task follows test-first development and ends with a focused Git commit.

---

## Planned File Structure

```text
backend/
  app/
    api/{auth,hosts,users,keys,scripts,jobs,health}.py
    core/{config,security,events}.py
    db/{base,session,models}.py
    schemas/{auth,host,user,script,job}.py
    services/{hosts,jobs,probes,runner}.py
    main.py
  ansible/
    playbook.yml
    roles/managed_user/tasks/main.yml
    roles/managed_user/templates/managed-sudoers.j2
  tests/{api,services,integration}/
  alembic/
  pyproject.toml
frontend/
  src/
    api/{client,types}.ts
    components/{app-shell,host-form,user-form,key-list,sync-wizard,job-log}.tsx
    features/{hosts,users,jobs,scripts}/
    pages/{dashboard,hosts,host-detail,users,user-detail,jobs,scripts,login}.tsx
    lib/{auth,utils}.ts
    App.tsx
  e2e/
  package.json
compose.yml
.env.example
README.md
docs/{deployment.md,operations.md}
```

### Task 1: Create the runnable skeleton and local configuration

**Files:**
- Create: `compose.yml`, `.env.example`, `backend/pyproject.toml`, `backend/app/main.py`, `backend/app/core/config.py`, `backend/app/api/health.py`, `backend/tests/api/test_health.py`, `frontend/package.json`, `frontend/src/main.tsx`, `frontend/src/App.tsx`
- Modify: `README.md`

**Interfaces:**
- Produces `GET /api/health` with `{ "status": "ok" }`.
- Produces Compose services `api` and `web`; `api` has mounted `./runtime` and a read-only `${SSH_KEY_PATH}` mount at `/run/secrets/control_ssh_key`.

- [ ] **Step 1: Write the failing backend health test**

```python
from fastapi.testclient import TestClient
from app.main import app

def test_health_returns_ok() -> None:
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run the test and verify it fails because the application is absent**

Run: `cd backend && pytest tests/api/test_health.py -q`

Expected: a collection error for missing `app.main`.

- [ ] **Step 3: Implement the minimal FastAPI application and health router**

```python
# backend/app/main.py
from fastapi import FastAPI
from app.api.health import router as health_router

app = FastAPI(title="Server Account Console")
app.include_router(health_router, prefix="/api")

# backend/app/api/health.py
from fastapi import APIRouter
router = APIRouter()

@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 4: Add Compose, environment example, Vite, and Chinese README setup instructions**

Set `DATABASE_URL=sqlite:////var/lib/server-account-console/app.db`, `CONTROL_SSH_KEY_PATH=/run/secrets/control_ssh_key`, `ADMIN_PASSWORD_HASH=`, `SESSION_SECRET=`, and `APP_ORIGIN=` in `.env.example`. Ensure the ignored `runtime/` volume is created by Compose rather than committed.

- [ ] **Step 5: Run the backend test and the container health check**

Run: `cd backend && pytest tests/api/test_health.py -q && cd .. && docker compose config`

Expected: one passing pytest test and a valid Compose configuration.

- [ ] **Step 6: Commit the skeleton**

```bash
git add compose.yml .env.example backend frontend README.md
git commit -m "feat: scaffold account console services"
```

### Task 2: Add SQLite persistence, migrations, and local administrator authentication

**Files:**
- Create: `backend/app/db/{base,session,models}.py`, `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/versions/001_initial.py`, `backend/app/core/security.py`, `backend/app/schemas/auth.py`, `backend/app/api/auth.py`, `backend/tests/api/test_auth.py`
- Modify: `backend/app/main.py`, `backend/app/core/config.py`, `backend/pyproject.toml`

**Interfaces:**
- Consumes `ADMIN_PASSWORD_HASH` and `SESSION_SECRET` from settings.
- Produces `POST /api/auth/login`, `POST /api/auth/logout`, and `GET /api/auth/me`.
- Produces dependency `require_admin(request: Request) -> None` for every non-auth API router.

- [ ] **Step 1: Write failing authentication tests**

```python
def test_login_sets_http_only_session(client):
    response = client.post("/api/auth/login", json={"password": "correct-horse"})
    assert response.status_code == 204
    assert "HttpOnly" in response.headers["set-cookie"]

def test_mutation_requires_authenticated_session(client):
    response = client.post("/api/hosts", json={})
    assert response.status_code == 401
```

- [ ] **Step 2: Run the tests and verify they fail with 404 or missing dependency**

Run: `cd backend && pytest tests/api/test_auth.py -q`

Expected: failure because authentication routes and host protection do not exist.

- [ ] **Step 3: Implement bcrypt verification and signed session cookies**

Use `passlib[bcrypt]` to compare the request password with `ADMIN_PASSWORD_HASH`; issue an `HttpOnly`, `SameSite=Lax` signed session cookie. Add a CSRF token endpoint and require `X-CSRF-Token` on authenticated unsafe methods. Do not create an administrator user table because the product has exactly one environment-provided administrator.

- [ ] **Step 4: Define initial SQLAlchemy models and create the Alembic migration**

Create UUID primary keys and UTC timestamps for `Host`, `ManagedUser`, `SshPublicKey`, `ScriptTemplate`, `Job`, `JobTarget`, and `HostUserState`. Add unique constraints for `managed_users.username`, `ssh_public_keys.fingerprint`, `script_templates.name`, and `(host_id, managed_user_id)` on `host_user_states`.

- [ ] **Step 5: Verify migration and authentication behavior**

Run: `cd backend && alembic upgrade head && pytest tests/api/test_auth.py -q`

Expected: migration completes and all authentication tests pass.

- [ ] **Step 6: Commit persistence and authentication**

```bash
git add backend
git commit -m "feat: add local admin authentication and database"
```

### Task 3: Implement host inventory, fingerprint confirmation, and SSH tests

**Files:**
- Create: `backend/app/schemas/host.py`, `backend/app/services/hosts.py`, `backend/app/api/hosts.py`, `backend/tests/services/test_hosts.py`, `backend/tests/api/test_hosts.py`
- Modify: `backend/app/db/models.py`, `backend/app/main.py`

**Interfaces:**
- Produces `HostCreate`, `HostUpdate`, and `HostRead` Pydantic schemas.
- Produces `probe_host(host: Host) -> HostProbeResult` containing `reachable`, `latency_ms`, and `fingerprint`.
- Produces `POST /api/hosts/{host_id}/test` and `POST /api/hosts/{host_id}/confirm-fingerprint`.

- [ ] **Step 1: Write failing host validation and fingerprint tests**

```python
def test_host_cannot_be_targeted_until_fingerprint_is_confirmed(client, host_payload):
    host = client.post("/api/hosts", json=host_payload).json()
    result = client.post(f"/api/hosts/{host['id']}/test")
    assert result.status_code == 200
    assert result.json()["requires_confirmation"] is True

def test_changed_fingerprint_marks_host_blocked(host, fake_probe):
    host.host_key_fingerprint = "SHA256:old"
    result = probe_host(host, ssh_probe=fake_probe("SHA256:new"))
    assert result.status == "fingerprint_changed"
```

- [ ] **Step 2: Run host tests and verify they fail**

Run: `cd backend && pytest tests/services/test_hosts.py tests/api/test_hosts.py -q`

Expected: import or route failures.

- [ ] **Step 3: Implement host CRUD and probe policy**

Validate port range 1-65535, unique non-archived host names, `ssh_user`, address, and normalized string tags. The probe may obtain a fingerprint but must not add it to a known-host file automatically. Confirmation stores the exact fingerprint. A later mismatch sets host status to `fingerprint_changed` and excludes it from job targets.

- [ ] **Step 4: Add a scheduled lightweight probe service**

Run TCP 22 plus authenticated SSH probe every five minutes while the API process is running. Persist status, latency, probe timestamp, and error summary. The worker must skip while an Ansible job holds the global runner lock.

- [ ] **Step 5: Run tests and manually validate API responses**

Run: `cd backend && pytest tests/services/test_hosts.py tests/api/test_hosts.py -q`

Expected: all host tests pass; confirmed and mismatched fingerprints have distinct states.

- [ ] **Step 6: Commit host inventory**

```bash
git add backend
git commit -m "feat: manage hosts and SSH fingerprints"
```

### Task 4: Implement managed users, multiple public keys, and script templates

**Files:**
- Create: `backend/app/schemas/{user,script}.py`, `backend/app/services/users.py`, `backend/app/api/{users,keys,scripts}.py`, `backend/tests/api/{test_users,test_keys,test_scripts}.py`
- Modify: `backend/app/main.py`, `backend/app/db/models.py`

**Interfaces:**
- Produces user CRUD under `/api/users`, public-key CRUD under `/api/users/{user_id}/keys`, and script-template CRUD under `/api/script-templates`.
- Produces `DesiredUserState` with `username`, `primary_group`, `groups`, `shell`, `home`, `sudo_rule`, and active public keys.

- [ ] **Step 1: Write failing validation tests**

```python
def test_rejects_invalid_linux_username(client):
    response = client.post("/api/users", json={"username": "not valid"})
    assert response.status_code == 422

def test_rejects_duplicate_public_key_fingerprint(client, user_id, public_key):
    assert client.post(f"/api/users/{user_id}/keys", json={"public_key": public_key}).status_code == 201
    response = client.post(f"/api/users/{user_id}/keys", json={"public_key": public_key})
    assert response.status_code == 409
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `cd backend && pytest tests/api/test_users.py tests/api/test_keys.py tests/api/test_scripts.py -q`

Expected: route failures.

- [ ] **Step 3: Implement desired-state CRUD with strict validation**

Accept Linux usernames matching `^[a-z_][a-z0-9_-]{0,31}$`. Parse OpenSSH public keys to compute their SHA256 fingerprint server-side; never trust a supplied fingerprint. Limit script templates to enabled/disabled versions with a name, Chinese description, and body. Increment the script version on each body update.

- [ ] **Step 4: Add user-to-host state reads**

Expose `GET /api/users/{user_id}/host-states` so the frontend can show last successful sync, desired hash, and any current host blockage next to selectable machines.

- [ ] **Step 5: Run the feature test suite**

Run: `cd backend && pytest tests/api/test_users.py tests/api/test_keys.py tests/api/test_scripts.py -q`

Expected: all validation, CRUD, and duplicate-detection tests pass.

- [ ] **Step 6: Commit identity management**

```bash
git add backend
git commit -m "feat: manage desired users keys and scripts"
```

### Task 5: Build the fixed Ansible role and Runner adapter

**Files:**
- Create: `backend/ansible/playbook.yml`, `backend/ansible/roles/managed_user/tasks/main.yml`, `backend/ansible/roles/managed_user/templates/managed-sudoers.j2`, `backend/app/services/runner.py`, `backend/tests/integration/test_managed_user_role.py`, `backend/tests/services/test_runner.py`
- Modify: `backend/pyproject.toml`, `compose.yml`

**Interfaces:**
- Produces `RunnerRequest(inventory: dict, extravars: dict, check: bool, artifact_dir: Path)`.
- Produces `run_playbook(request: RunnerRequest, on_event: Callable[[dict], None]) -> RunnerResult`.
- Accepts only structured variable `desired_user` and an optional, snapshotted `post_script_path`.

- [ ] **Step 1: Write an integration test against an ephemeral SSH-enabled Linux container**

```python
def test_role_is_idempotent_and_preserves_unmanaged_key(ssh_target, runner_request):
    first = run_playbook(runner_request)
    second = run_playbook(runner_request)
    assert first.status == "successful"
    assert second.changed_hosts == []
    assert ssh_target.authorized_keys_contains("unmanaged-key")
```

- [ ] **Step 2: Run the integration test and verify it fails before the role exists**

Run: `cd backend && pytest tests/integration/test_managed_user_role.py -q`

Expected: missing playbook or runner adapter failure.

- [ ] **Step 3: Implement the declarative role**

Use Ansible modules for group, user, file, authorized_key, template, and command execution. The role must create the primary and supplemental groups; create/update the user and home; set `.ssh` mode `0700`; write managed keys without `exclusive: true`; manage a validated sudoers file mode `0440`; create configured directories and symlinks; then execute the snapshotted post script with a JSON input file. Use `become: true` and no raw string interpolation of API data.

- [ ] **Step 4: Implement Runner artifact isolation and event normalization**

Use an execution-scoped temporary private-data directory. Translate only redacted Ansible events into `{ timestamp, host_id, level, event, message }` before persistence, then delete the complete Runner tree so inventory, extra vars and inherited environment never become artifacts.

- [ ] **Step 5: Re-run idempotence and runner unit tests**

Run: `cd backend && pytest tests/services/test_runner.py tests/integration/test_managed_user_role.py -q`

Expected: both the initial change and no-change rerun assertions pass.

- [ ] **Step 6: Commit Ansible automation**

```bash
git add backend/ansible backend/app/services/runner.py backend/tests
git commit -m "feat: apply managed user state with ansible"
```

### Task 6: Implement preview, confirmation, execution, persistence, and SSE job events

**Files:**
- Create: `backend/app/schemas/job.py`, `backend/app/services/{jobs,events}.py`, `backend/app/api/jobs.py`, `backend/tests/services/test_jobs.py`, `backend/tests/api/test_jobs.py`
- Modify: `backend/app/db/models.py`, `backend/app/main.py`, `backend/app/services/runner.py`

**Interfaces:**
- Produces `POST /api/jobs/preview`, `POST /api/jobs/{job_id}/execute`, `POST /api/jobs/{job_id}/rerun`, `GET /api/jobs`, `GET /api/jobs/{job_id}`, and `GET /api/jobs/{job_id}/events`.
- Produces job states `preview_running`, `ready_to_confirm`, `preview_failed`, `running`, `succeeded`, `partial_failed`, and `expired`.

- [ ] **Step 1: Write failing job state tests**

```python
def test_only_ready_preview_can_execute(service, preview_job):
    preview_job.state = "preview_running"
    with pytest.raises(JobStateError):
        service.execute(preview_job.id)

def test_execution_uses_immutable_snapshot(service, ready_preview):
    job = service.execute(ready_preview.id)
    assert job.request_snapshot == ready_preview.request_snapshot
    assert job.script_snapshot == ready_preview.script_snapshot
```

- [ ] **Step 2: Run tests and verify state transitions fail**

Run: `cd backend && pytest tests/services/test_jobs.py tests/api/test_jobs.py -q`

Expected: missing service and endpoint failures.

- [ ] **Step 3: Implement global lock, snapshotting, and expiration**

Acquire a SQLite transaction-backed singleton lock before preview or execution and release it in `finally`. Reject competing attempts with HTTP 409. Snapshot selected hosts, active keys, desired user fields, script body/version, and desired hash before Runner starts. A background sweep marks `ready_to_confirm` jobs older than 30 minutes as `expired`.

- [ ] **Step 4: Implement per-target results and SSE replay**

Create one `JobTarget` before Runner starts each host. Persist normalized events; stream persisted events first and then live events so reconnecting clients do not lose output. Continue execution after per-host failure and calculate `succeeded` or `partial_failed` only after all selected targets end.

- [ ] **Step 5: Run API and state-machine tests**

Run: `cd backend && pytest tests/services/test_jobs.py tests/api/test_jobs.py -q`

Expected: tests cover preview expiry, invalid confirmation, lock conflict, partial failure, snapshot immutability, and SSE replay.

- [ ] **Step 6: Commit task orchestration**

```bash
git add backend
git commit -m "feat: add previewed sync jobs and event stream"
```

### Task 7: Scaffold the React application shell, session handling, and typed API client

**Files:**
- Create: `frontend/src/api/{client,types}.ts`, `frontend/src/lib/auth.ts`, `frontend/src/components/app-shell.tsx`, `frontend/src/pages/{login,dashboard}.tsx`, `frontend/src/test/setup.ts`, `frontend/src/pages/login.test.tsx`
- Modify: `frontend/src/{main,App}.tsx`, `frontend/package.json`

**Interfaces:**
- Produces `api<T>(path: string, init?: RequestInit): Promise<T>` that sends credentials and CSRF token.
- Produces app routes `/login`, `/`, `/hosts`, `/users`, `/jobs`, `/scripts`.
- Consumes `GET /api/auth/me` and `POST /api/auth/login`.

- [ ] **Step 1: Write a failing login form test**

```tsx
it("submits a password then navigates to the dashboard", async () => {
  render(<LoginPage />)
  await userEvent.type(screen.getByLabelText("管理员密码"), "correct-horse")
  await userEvent.click(screen.getByRole("button", { name: "登录" }))
  expect(await screen.findByText("机器概览")).toBeVisible()
})
```

- [ ] **Step 2: Run the test and verify it fails before the page exists**

Run: `cd frontend && npm test -- login.test.tsx`

Expected: missing component or test failure.

- [ ] **Step 3: Implement Vite, shadcn/ui, Router, Query client, and shell**

Use a restrained operations-console layout: persistent left navigation, compact top status line, responsive main content, and no marketing/hero content. Route unauthenticated sessions to `/login`; provide logout in the shell. Implement Chinese loading, empty, authorization, and API-error states.

- [ ] **Step 4: Run frontend unit tests and production build**

Run: `cd frontend && npm test -- --run && npm run build`

Expected: tests pass and Vite produces `dist/`.

- [ ] **Step 5: Commit frontend foundation**

```bash
git add frontend
git commit -m "feat: add frontend shell and login"
```

### Task 8: Implement machine, user, key, and script-template management screens

**Files:**
- Create: `frontend/src/features/{hosts,users,scripts}/queries.ts`, `frontend/src/components/{host-form,user-form,key-list}.tsx`, `frontend/src/pages/{hosts,host-detail,users,user-detail,scripts}.tsx`, `frontend/src/pages/users.test.tsx`, `frontend/src/pages/hosts.test.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/api/types.ts`

**Interfaces:**
- Consumes all CRUD endpoints from Tasks 3 and 4.
- Produces `HostSelectionRow` and `ManagedUserFormValues` types used by the sync wizard.

- [ ] **Step 1: Write failing user-detail interaction tests**

```tsx
it("adds a valid public key and shows its fingerprint", async () => {
  render(<UserDetailPage />)
  await userEvent.type(screen.getByLabelText("SSH 公钥"), validEd25519Key)
  await userEvent.click(screen.getByRole("button", { name: "添加公钥" }))
  expect(await screen.findByText("SHA256:")).toBeVisible()
})
```

- [ ] **Step 2: Run screen tests and verify they fail**

Run: `cd frontend && npm test -- hosts.test.tsx users.test.tsx`

Expected: missing pages and forms.

- [ ] **Step 3: Implement dense CRUD screens with validated forms**

Use shadcn tables, dialogs, form controls, badges, tooltips, and destructive-action confirmation dialogs. The hosts list shows `unconfirmed`, `reachable`, `unreachable`, and `fingerprint_changed` visually. The user detail shows active-key count and host state table. The scripts screen explicitly warns that a template runs after account synchronization.

- [ ] **Step 4: Run page tests and build**

Run: `cd frontend && npm test -- --run && npm run build`

Expected: all CRUD page tests pass and build succeeds.

- [ ] **Step 5: Commit inventory and desired-state UI**

```bash
git add frontend
git commit -m "feat: add host user key and script screens"
```

### Task 9: Implement the manual target-selection, preview, confirmation, and job-log UI

**Files:**
- Create: `frontend/src/components/{sync-wizard,job-log}.tsx`, `frontend/src/features/jobs/{queries,use-job-events}.ts`, `frontend/src/pages/jobs.tsx`, `frontend/src/pages/job-detail.tsx`, `frontend/src/components/sync-wizard.test.tsx`
- Modify: `frontend/src/pages/user-detail.tsx`, `frontend/src/App.tsx`, `frontend/src/api/types.ts`

**Interfaces:**
- Consumes `POST /api/jobs/preview`, `POST /api/jobs/{id}/execute`, `GET /api/jobs/{id}/events`, and job detail endpoints.
- Produces `SyncWizard` opened from user detail and initialized with the selected user ID.

- [ ] **Step 1: Write a failing confirmation-gate test**

```tsx
it("cannot execute until a successful preview is confirmed", async () => {
  render(<SyncWizard userId="user-1" />)
  await userEvent.click(screen.getByLabelText("host-a"))
  await userEvent.click(screen.getByRole("button", { name: "执行预检" }))
  expect(await screen.findByText("预检完成")).toBeVisible()
  expect(screen.getByRole("button", { name: "确认并执行" })).toBeDisabled()
  await userEvent.click(screen.getByLabelText("我已确认以上变更"))
  expect(screen.getByRole("button", { name: "确认并执行" })).toBeEnabled()
})
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `cd frontend && npm test -- sync-wizard.test.tsx`

Expected: missing wizard failure.

- [ ] **Step 3: Implement three-step synchronization UI**

Step one renders only targetable hosts as selectable rows and explains blocked host reasons. Step two chooses zero or one enabled script template. Step three renders per-host preview results, then requires an explicit confirmation checkbox. The execution view subscribes to SSE, groups logs by host, retains logs after reconnect, and exposes a safe “以相同输入重新预检” action after terminal states.

- [ ] **Step 4: Add job list and detail result states**

Show `preview_failed`, `expired`, `succeeded`, and `partial_failed` with stable badges. Display the frozen task snapshot and exact script version used, not the current mutable template.

- [ ] **Step 5: Run tests and a production build**

Run: `cd frontend && npm test -- --run && npm run build`

Expected: wizard gating and log-rendering tests pass.

- [ ] **Step 6: Commit the primary workflow**

```bash
git add frontend
git commit -m "feat: add reviewed manual sync workflow"
```

### Task 10: Add operational safeguards, backups, and deployment documentation

**Files:**
- Create: `backend/app/services/backup.py`, `backend/app/api/health.py` additions, `backend/tests/services/test_backup.py`, `docs/{deployment,operations}.md`, `scripts/backup.sh`
- Modify: `compose.yml`, `.env.example`, `README.md`

**Interfaces:**
- Produces `GET /api/health` with database and runner readiness fields.
- Produces a daily SQLite backup under ignored `runtime/backups/` with a 14-day retention policy.

- [ ] **Step 1: Write failing backup retention and health tests**

```python
def test_backup_removes_files_older_than_14_days(tmp_path):
    create_backup(tmp_path, now=utc_now())
    remove_expired_backups(tmp_path, now=utc_now() + timedelta(days=15))
    assert list(tmp_path.glob("*.db")) == []
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `cd backend && pytest tests/services/test_backup.py -q`

Expected: missing backup implementation failure.

- [ ] **Step 3: Implement backup and readiness behavior**

Use SQLite online backup APIs or a safe `sqlite3 .backup` invocation after ensuring the database directory exists. Do not include the SSH private key in any backup. Health returns `ok` only when SQLite is usable and the mounted private-key path exists and is unreadable by group/other.

- [ ] **Step 4: Write deployment and operations documentation**

Document: generating bcrypt hash; setting `.env`; mounting a `0600` SSH key; creating runtime directories; first admin login; adding and confirming host fingerprints; backup restoration; runner artifact cleanup; and response to a fingerprint change. Use internal-network firewall and reverse-proxy TLS guidance.

- [ ] **Step 5: Verify documentation commands and tests**

Run: `cd backend && pytest tests/services/test_backup.py -q && cd .. && docker compose config`

Expected: backup test passes and Compose configuration validates.

- [ ] **Step 6: Commit deployment safeguards**

```bash
git add backend compose.yml .env.example README.md docs scripts
git commit -m "docs: add secure deployment and backup guidance"
```

### Task 11: Execute end-to-end verification and prepare the first release

**Files:**
- Create: `frontend/e2e/sync-flow.spec.ts`, `backend/tests/integration/test_security_redaction.py`, `docs/release-checklist.md`
- Modify: `README.md`

**Interfaces:**
- Consumes the complete API, Runner adapter, and frontend workflow.
- Produces a repeatable release gate for a one-user, internal deployment.

- [ ] **Step 1: Write a failing private-key redaction test and browser workflow**

```python
def test_runner_events_never_contain_private_key_material(runner_result, private_key_text):
    assert private_key_text not in "\n".join(event.message for event in runner_result.events)
```

```ts
test("admin previews, confirms, and reviews a partial sync", async ({ page }) => {
  await page.goto("/users/alice")
  await page.getByRole("button", { name: "同步到机器" }).click()
  await page.getByLabel("host-a").check()
  await page.getByLabel("host-b").check()
  await page.getByRole("button", { name: "执行预检" }).click()
  await page.getByLabel("我已确认以上变更").check()
  await page.getByRole("button", { name: "确认并执行" }).click()
  await expect(page.getByText("部分失败")).toBeVisible()
})
```

- [ ] **Step 2: Run the tests and verify they fail before fixtures are complete**

Run: `cd backend && pytest tests/integration/test_security_redaction.py -q && cd ../frontend && npx playwright test e2e/sync-flow.spec.ts`

Expected: fixture or flow failure until final test environment is wired.

- [ ] **Step 3: Implement deterministic test fixtures and the release checklist**

Use two SSH test targets: one successful and one intentionally unreachable or script-failing target. The release checklist verifies the five MVP acceptance criteria, database backup restore, host fingerprint blocking, public-key redaction, and no uncommitted secrets.

- [ ] **Step 4: Run the full quality gate**

Run: `cd backend && pytest -q && cd ../frontend && npm test -- --run && npm run build && npx playwright test`

Expected: all backend, frontend, build, and browser checks pass.

- [ ] **Step 5: Commit verification artifacts and tag the release**

```bash
git add backend frontend docs README.md
git commit -m "test: add end-to-end release coverage"
git tag -a v0.1.0 -m "Initial account console MVP"
git push origin main --tags
```

## Plan Self-Review

### Spec coverage

- Manual host selection, preview, explicit confirmation, runner execution, per-host logs, immutable snapshots, safe reruns, and task records are covered by Tasks 5, 6, and 9.
- Machine and user visibility, SSH keys, scripts, fingerprints, and basic SSH health are covered by Tasks 3, 4, and 8.
- Single-admin security, private-key isolation, concurrency, timeouts, backups, and operations guidance are covered by Tasks 2, 6, and 10.
- Idempotence, failure continuation, redaction, API testing, integration testing, browser testing, and release acceptance are covered by Tasks 5, 6, and 11.
- Full CPU/memory/disk monitoring remains explicitly deferred, consistent with the approved MVP scope.

### Placeholder and consistency check

No unresolved placeholder markers or undefined interface references remain. `RunnerRequest`, `DesiredUserState`, `HostSelectionRow`, job routes, and job states are introduced before their consumers. The plan uses `ready_to_confirm` consistently as the only confirmation-eligible state.
