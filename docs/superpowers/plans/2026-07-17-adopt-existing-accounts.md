# Adopt Existing Accounts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an administrator associate existing Linux accounts with members, append and later revoke only platform-managed SSH keys, and inspect equivalent commands before confirming any access job.

**Architecture:** Extend `HostAccessGrant` with account origin and observed remote identity fields. Reuse host inventory for selection, branch the fixed Ansible access role by origin, and freeze shell-quoted equivalent commands into the job snapshot for review without executing those strings.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic, Ansible Runner, React 19, TypeScript, Vitest, pytest.

## Global Constraints

- Adopted accounts keep their existing UID, groups, shell, home, and data.
- Provisioning adopted accounts only appends enabled member public keys and unlocks the account.
- Revoking adopted accounts removes only recorded platform keys, then locks the account.
- Existing public keys are never replaced or removed during provisioning.
- Equivalent command previews contain no private key, sudo password, or credential material.
- Actual execution continues through fixed Ansible modules, never arbitrary preview text.

---

### Task 1: Persist Adopted Account Ownership

**Files:**
- Modify: `backend/app/db/models.py`
- Create: `backend/alembic/versions/006_adopt_existing_accounts.py`
- Modify: `backend/tests/test_models.py`

**Interfaces:**
- Produces: `HostAccessGrant.account_origin`, `remote_uid`, `remote_primary_group`, `remote_home`, `managed_public_keys`, and nullable `data_directory`.

- [ ] **Step 1: Write the failing model test** that creates an adopted grant with `data_directory=None` and verifies all observed identity fields and managed keys round-trip.
- [ ] **Step 2: Run** `cd backend && .venv/bin/pytest tests/test_models.py -q`; expect failure because the mapped fields do not exist.
- [ ] **Step 3: Add mapped columns and migration**. Migration `006` adds non-null `account_origin` with server default `created`, nullable observed fields, non-null JSON `managed_public_keys` with `[]`, and makes `data_directory` nullable.
- [ ] **Step 4: Run the focused model test** and expect it to pass.

### Task 2: Build Frozen Equivalent Command Previews

**Files:**
- Create: `backend/app/services/command_previews.py`
- Create: `backend/tests/services/test_command_previews.py`
- Modify: `backend/app/services/access_grants.py`

**Interfaces:**
- Produces: `build_grant_command_preview(operation: str, grant: dict, public_keys: list[str]) -> dict` returning `tasks`, `commands`, `warnings`, and public key fingerprints.
- Consumes: normalized grant snapshot and enabled member public keys.

- [ ] **Step 1: Write failing tests** proving every username, path, group, sudo rule, and public key is quoted with `shlex.quote`; adopted provision previews append and unlock without `useradd`, `rm`, or home migration; adopted revoke previews remove only recorded keys and run `usermod -L`.
- [ ] **Step 2: Run** `cd backend && .venv/bin/pytest tests/services/test_command_previews.py -q`; expect import failure.
- [ ] **Step 3: Implement the pure preview builder** with separate created/adopted provision and revoke branches. Label output as equivalent commands and include the lock warning for adopted revoke.
- [ ] **Step 4: Attach the preview dictionary to each grant snapshot** before the `Job` is committed.
- [ ] **Step 5: Run the focused tests** and expect all to pass.

### Task 3: Accept and Validate Existing Account Selections

**Files:**
- Modify: `backend/app/schemas/access_grant.py`
- Modify: `backend/app/services/access_grants.py`
- Modify: `backend/app/api/access_grants.py`
- Modify: `backend/tests/api/test_access_grants.py`

**Interfaces:**
- Produces: `ExistingAccountSnapshot(uid: int, primary_group: str, home: str)` and `AccessGrantProvisionRow.account_origin`.
- Produces API serialization fields for account origin, remote identity, managed key fingerprints, and optional data directory.

- [ ] **Step 1: Write failing API tests** for an adopted row that succeeds without `Host.data_root`, rejects missing/non-absolute existing home, rejects username ownership collisions, stores observed identity values, and returns command previews.
- [ ] **Step 2: Run the exact new tests** and confirm 422/current-schema failures.
- [ ] **Step 3: Add request and response schemas** using `Literal["created", "adopted"]`; require `existing_account` only for adopted rows and reject it for created rows.
- [ ] **Step 4: Update job creation** so only created rows require data root and permission templates; adopted rows freeze observed identity, ignore template mutation fields, and include current member keys.
- [ ] **Step 5: Update grant serialization** to expose origin, remote identity, optional data directory, and fingerprints without exposing secrets.
- [ ] **Step 6: Run** `cd backend && .venv/bin/pytest tests/api/test_access_grants.py -q` and expect all tests to pass.

### Task 4: Execute Safe Adopted Provision and Revoke

**Files:**
- Modify: `backend/ansible/roles/access_grant/tasks/main.yml`
- Create: `backend/ansible/roles/access_grant/tasks/provision_adopted.yml`
- Rename/retain: `backend/ansible/roles/access_grant/tasks/provision.yml` as the created-account branch
- Create: `backend/ansible/roles/access_grant/tasks/revoke_adopted.yml`
- Modify: `backend/ansible/roles/access_grant/tasks/revoke.yml`
- Modify: `backend/app/services/jobs.py`
- Modify: `backend/tests/services/test_jobs.py`

**Interfaces:**
- Consumes: grant snapshot `account_origin`, observed identity, `managed_public_keys`, and `access_grant_user.public_keys`.
- Produces: finalized grant ownership and managed key set only for succeeded targets.

- [ ] **Step 1: Write failing service tests** proving successful adopted provision persists origin/identity/public keys and adopted revoke snapshots use the grant's recorded keys, not the member's current key set.
- [ ] **Step 2: Run focused service tests** and confirm missing-field/current-behavior failures.
- [ ] **Step 3: Implement adopted Ansible tasks**: getent and assert UID/group/home; unlock; ensure original-home `.ssh`; append keys with `ansible.posix.authorized_key` semantics available in core-compatible tasks; never modify groups, shell, sudo, or home.
- [ ] **Step 4: Implement adopted revoke tasks**: revalidate account identity, remove only recorded key strings, lock account, and never remove files or the account.
- [ ] **Step 5: Update finalization** to persist managed keys on provision and preserve them for audit after revoke. Keep created-account behavior unchanged.
- [ ] **Step 6: Run** `cd backend && .venv/bin/pytest tests/services/test_jobs.py tests/api/test_access_grants.py -q` and `cd backend && .venv/bin/ansible-playbook --syntax-check -i 'localhost,' ansible/access_grant.yml`.

### Task 5: Add Existing Account Selection to the Member Workbench

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: `GET /hosts/{host_id}/users`, extended provision request, and extended grant/job snapshots.
- Produces: per-host create/adopt mode with an existing-account selector and observed account summary.

- [ ] **Step 1: Write failing UI tests** that switch a row to “纳管已有账号”, load host users, select one, and submit its UID/group/home while omitting data-directory and permission mutations.
- [ ] **Step 2: Run** `cd frontend && npm test -- --run src/App.test.tsx`; expect the new controls not to exist.
- [ ] **Step 3: Extend TypeScript types** for grant origin, remote identity, optional data directory, managed fingerprints, and command preview.
- [ ] **Step 4: Add a segmented account-mode control**. Fetch inventory only when adoption is selected, show loading/error states, filter system accounts below UID 1000 except an explicitly selected account, and render UID/home/lock/key-count metadata.
- [ ] **Step 5: Disable template and data-root requirements for adopted rows** while retaining reachable/verified host gating.
- [ ] **Step 6: Run the focused UI tests** and expect them to pass.

### Task 6: Require Visible Command Review Before Confirmation

**Files:**
- Create: `frontend/src/CommandReview.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/e2e/sync-flow.spec.ts`

**Interfaces:**
- Consumes: immutable `request_snapshot.grants[].command_preview` and `Job.targets`.
- Produces: reusable command review for member workbench and execution records.

- [ ] **Step 1: Write failing tests** proving a ready job renders target commands and warnings, the execute button remains disabled until “我已审阅以上命令” is checked, and execution records preserve the same review after reload.
- [ ] **Step 2: Run focused Vitest** and verify expected missing-content failures.
- [ ] **Step 3: Build `CommandReview`** as an unframed per-target disclosure list with task summary, fingerprints, warnings, copyable `<pre>` commands, target error, and explicit “等价命令，实际由 Ansible 模块执行” text.
- [ ] **Step 4: Replace both compact confirmation strips** with the shared review component. A ready job without command previews must not be executable and must ask for a fresh preview.
- [ ] **Step 5: Update Playwright mocks and flow** to inspect a visible command before confirmation.
- [ ] **Step 6: Run** `cd frontend && npm test -- --run` and `cd frontend && npm run build`.

### Task 7: Migrate, Verify, and Run Locally

**Files:**
- Modify: `README.md` or `docs/operations.md` only if operator behavior changed beyond existing instructions.

**Interfaces:**
- Produces: upgraded local database and refreshed tmux services on `127.0.0.1:8003` and `0.0.0.0:5174`.

- [ ] **Step 1: Run migration** with the backend environment against the configured local database and inspect the new columns.
- [ ] **Step 2: Run full verification**: `cd backend && .venv/bin/pytest -q`, Alembic upgrade on a copied database, `cd frontend && npm test -- --run`, and `cd frontend && npm run build`.
- [ ] **Step 3: Restart tmux services** without changing ports, then verify `/api/health` through the Vite proxy and load the page at `http://<host>:5174`.
- [ ] **Step 4: Review `git diff --check` and `git status`**, commit to `main` with the configured `jkzhang` identity, and push only after all verification succeeds.
