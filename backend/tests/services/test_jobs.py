from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.models import Host, HostAccessGrant, HostCredential, Job, JobTarget, ManagedUser, SshPublicKey
from app.db.session import SessionLocal
from app.services import jobs
from app.services.credentials import CredentialCipher
from app.services.jobs import (
    JobStateError,
    apply_runner_events,
    create_and_start_job,
    ensure_executable,
    expire_ready_previews,
    finalize_host_user_states,
    utc_now,
)
from app.services.runner import RunnerResult, redact_event


def test_only_ready_preview_can_execute() -> None:
    with pytest.raises(JobStateError):
        ensure_executable("preview_running")

    ensure_executable("ready_to_confirm")


def test_failed_preview_finishes_when_fingerprint_validation_fails(monkeypatch) -> None:
    with SessionLocal() as session:
        job = Job(kind="sync", state="preview_running")
        session.add(job)
        session.commit()

        def fail(*_args, **_kwargs):
            raise JobStateError("主机 lab-01 的指纹校验失败")

        monkeypatch.setattr(jobs, "_run_job", fail)
        result = jobs.execute_job(session, job, check=True)

        assert result.state == "preview_failed"
        assert result.finished_at is not None


def test_ready_preview_expires_after_thirty_minutes() -> None:
    with SessionLocal() as session:
        job = Job(kind="sync", state="ready_to_confirm", finished_at=utc_now() - timedelta(minutes=31))
        session.add(job)
        session.commit()

        assert expire_ready_previews(session, now=utc_now()) == 1
        assert session.get(Job, job.id).state == "expired"


def test_runner_failure_only_marks_the_affected_target() -> None:
    with SessionLocal() as session:
        first = Host(name="lab-01", address="192.0.2.10")
        second = Host(name="lab-02", address="192.0.2.11")
        job = Job(
            kind="sync",
            state="running",
            request_snapshot={"hosts": [{"id": "first", "name": "lab-01"}, {"id": "second", "name": "lab-02"}]},
        )
        session.add_all([first, second, job])
        session.flush()
        session.add_all([
            JobTarget(job_id=job.id, host_id=first.id, state="pending"),
            JobTarget(job_id=job.id, host_id=second.id, state="pending"),
        ])
        session.commit()

        apply_runner_events(session, job, [{"event": "runner_on_failed", "stdout": "permission denied", "event_data": {"host": "lab-02"}}])

        targets = {target.host_id: target for target in session.scalars(select(JobTarget).where(JobTarget.job_id == job.id))}
        assert targets[first.id].state == "pending"
        assert targets[second.id].state == "failed"
        assert targets[second.id].error == "permission denied"


def test_nonzero_runner_marks_unresolved_targets_failed() -> None:
    with SessionLocal() as session:
        host = Host(name="lab-01", address="192.0.2.10")
        job = Job(kind="sync", state="running")
        session.add_all([host, job])
        session.flush()
        session.add(JobTarget(job_id=job.id, host_id=host.id, state="pending"))
        session.commit()

        targets = jobs._finish_pending_targets(session, job, failure_message="Ansible 以非零状态退出")

        assert targets[0].state == "failed"
        assert targets[0].error == "Ansible 以非零状态退出"


def test_successful_targets_update_user_host_state() -> None:
    with SessionLocal() as session:
        host = Host(name="lab-01", address="192.0.2.10")
        user = ManagedUser(username="alice", home="/home/alice")
        job = Job(kind="sync", state="succeeded", request_snapshot={"user_id": "placeholder"})
        session.add_all([host, user, job])
        session.flush()
        job.request_snapshot = {"user_id": user.id}
        session.add(JobTarget(job_id=job.id, host_id=host.id, state="succeeded"))
        session.commit()

        finalize_host_user_states(session, job, desired_hash="desired-state-hash")

        state = session.execute(select(jobs.HostUserState).where(jobs.HostUserState.host_id == host.id)).scalar_one()
        assert state.last_success_job_id == job.id
        assert state.desired_hash == "desired-state-hash"


def test_successful_access_grant_targets_update_only_matching_grants() -> None:
    with SessionLocal() as session:
        host = Host(name="gpu-01", address="192.0.2.10", data_root="/mnt/train")
        user = ManagedUser(username="alice")
        job = Job(
            kind="access_grant_provision",
            state="succeeded",
            user_snapshot={"id": "placeholder", "public_keys": ["ssh-ed25519 AAAA alice"]},
            request_snapshot={"user_id": "placeholder", "operation": "provision", "grants": []},
        )
        session.add_all([host, user, job])
        session.flush()
        job.user_snapshot = {"id": user.id, "public_keys": ["ssh-ed25519 AAAA alice"]}
        job.request_snapshot = {
            "user_id": user.id,
            "operation": "provision",
            "grants": [{
                "host_id": host.id,
                "username": "alice-gpu",
                "permission_template_id": None,
                "template": {"name": "自定义", "groups": ["docker"], "sudo_rule": None},
                "groups_override": ["docker"],
                "sudo_rule_override": None,
                "data_directory": "/mnt/train/alice-gpu",
            }],
        }
        session.add(JobTarget(job_id=job.id, host_id=host.id, state="succeeded"))
        session.commit()

        jobs.finalize_access_grants(session, job)

        grant = session.scalar(select(HostAccessGrant).where(HostAccessGrant.host_id == host.id))
        assert grant is not None
        assert grant.username == "alice-gpu"
        assert grant.data_directory == "/mnt/train/alice-gpu"
        assert grant.last_success_job_id == job.id


def test_successful_adopted_grant_preserves_identity_and_accumulates_managed_keys() -> None:
    with SessionLocal() as session:
        host = Host(name="gpu-adopted", address="192.0.2.31")
        user = ManagedUser(username="alice")
        job = Job(
            kind="access_grant_provision",
            state="succeeded",
            user_snapshot={
                "id": "placeholder",
                "public_keys": ["ssh-ed25519 AAAA current"],
                "key_fingerprints": ["SHA256:current"],
            },
            request_snapshot={"user_id": "placeholder", "operation": "provision", "grants": []},
        )
        session.add_all([host, user, job])
        session.flush()
        existing = HostAccessGrant(
            host_id=host.id,
            managed_user_id=user.id,
            username="legacy-alice",
            account_origin="adopted",
            remote_uid=1007,
            remote_primary_group="research",
            remote_home="/srv/homes/legacy-alice",
            managed_public_keys=["ssh-ed25519 AAAA previous"],
            managed_key_fingerprints=["SHA256:previous"],
            data_directory=None,
        )
        session.add(existing)
        job.user_snapshot = {
            "id": user.id,
            "public_keys": ["ssh-ed25519 AAAA current"],
            "key_fingerprints": ["SHA256:current"],
        }
        job.request_snapshot = {
            "user_id": user.id,
            "operation": "provision",
            "grants": [{
                "host_id": host.id,
                "username": "legacy-alice",
                "account_origin": "adopted",
                "permission_template_id": None,
                "template": {"name": "保留已有权限", "groups": [], "sudo_rule": None},
                "groups_override": None,
                "sudo_rule_override": None,
                "data_directory": None,
                "remote_uid": 1007,
                "remote_primary_group": "research",
                "remote_home": "/srv/homes/legacy-alice",
            }],
        }
        session.add(JobTarget(job_id=job.id, host_id=host.id, state="succeeded"))
        session.commit()

        jobs.finalize_access_grants(session, job)

        session.refresh(existing)
        assert existing.account_origin == "adopted"
        assert existing.remote_uid == 1007
        assert existing.remote_primary_group == "research"
        assert existing.remote_home == "/srv/homes/legacy-alice"
        assert existing.data_directory is None
        assert existing.managed_public_keys == ["ssh-ed25519 AAAA previous", "ssh-ed25519 AAAA current"]
        assert existing.managed_key_fingerprints == ["SHA256:previous", "SHA256:current"]


def test_successful_adopted_revoke_keeps_key_audit_while_marking_grant_revoked() -> None:
    with SessionLocal() as session:
        host = Host(name="gpu-adopted-revoke", address="192.0.2.32")
        user = ManagedUser(username="alice")
        session.add_all([host, user])
        session.flush()
        grant = HostAccessGrant(
            host_id=host.id,
            managed_user_id=user.id,
            username="legacy-alice",
            account_origin="adopted",
            remote_uid=1007,
            remote_primary_group="research",
            remote_home="/srv/homes/legacy-alice",
            managed_public_keys=["ssh-ed25519 AAAA managed"],
            managed_key_fingerprints=["SHA256:managed"],
            data_directory=None,
        )
        job = Job(kind="access_grant_revoke", state="succeeded", user_snapshot={}, request_snapshot={})
        session.add_all([grant, job])
        session.flush()
        job.request_snapshot = {
            "user_id": user.id,
            "operation": "revoke",
            "grants": [{"grant_id": grant.id, "host_id": host.id, "account_origin": "adopted"}],
        }
        session.add(JobTarget(job_id=job.id, host_id=host.id, state="succeeded"))
        session.commit()

        jobs.finalize_access_grants(session, job)

        session.refresh(grant)
        assert grant.state == "revoked"
        assert grant.managed_public_keys == ["ssh-ed25519 AAAA managed"]
        assert grant.managed_key_fingerprints == ["SHA256:managed"]


def test_lock_conflict_does_not_create_an_orphan_preview() -> None:
    assert jobs.RUNNER_LOCK.acquire(blocking=False)
    try:
        with SessionLocal() as session:
            with pytest.raises(JobStateError, match="已有任务正在运行"):
                create_and_start_job(session, None, [], None, check=True)
            assert list(session.scalars(select(Job))) == []
    finally:
        jobs.RUNNER_LOCK.release()


def test_sync_requires_host_credential_with_verified_ssh_and_sudo() -> None:
    with SessionLocal() as session:
        host = Host(name="lab-01", address="192.0.2.10", status="reachable")
        user = ManagedUser(username="alice", home="/home/alice")
        session.add_all([host, user])
        session.flush()
        session.add_all([
            SshPublicKey(managed_user_id=user.id, public_key="ssh-ed25519 AAAA managed", fingerprint="SHA256:managed", comment="managed"),
            HostCredential(host_id=host.id, private_key_ciphertext="cipher", sudo_password_ciphertext="cipher", ssh_verified=True, sudo_verified=False),
        ])
        session.commit()

        with pytest.raises(JobStateError, match="连接凭证尚未通过 SSH 和 sudo 验证"):
            jobs.create_job(session, user, [host], None)


def test_sync_execution_rechecks_current_host_credential(monkeypatch) -> None:
    with SessionLocal() as session:
        host = Host(name="lab-execute", address="192.0.2.21", status="reachable", host_key_fingerprint="SHA256:known")
        job = Job(
            kind="sync",
            state="ready_to_confirm",
            request_snapshot={"hosts": [{"id": "placeholder", "name": host.name}]},
        )
        session.add_all([host, job])
        session.flush()
        job.request_snapshot = {"hosts": [{"id": host.id, "name": host.name}]}
        session.add(HostCredential(host_id=host.id, private_key_ciphertext="cipher", sudo_password_ciphertext="cipher", ssh_verified=True, sudo_verified=False))
        session.commit()
        monkeypatch.setattr(jobs, "_launch_worker", lambda *_args: (_ for _ in ()).throw(AssertionError("凭证失效时不得执行")))

        with pytest.raises(JobStateError, match="连接凭证尚未通过 SSH 和 sudo 验证"):
            jobs.start_job(session, job, check=False)

        assert session.get(Job, job.id).state == "ready_to_confirm"


def test_access_grant_execution_rejects_a_changed_data_root(monkeypatch) -> None:
    with SessionLocal() as session:
        host = Host(name="gpu-root-check", address="192.0.2.24", data_root="/mnt/new", status="reachable", host_key_fingerprint="SHA256:known")
        user = ManagedUser(username="alice")
        job = Job(
            kind="access_grant_provision",
            state="ready_to_confirm",
            user_snapshot={"id": "placeholder", "public_keys": ["ssh-ed25519 AAAA alice"]},
            request_snapshot={"user_id": "placeholder", "hosts": [], "grants": []},
        )
        session.add_all([host, user, job])
        session.flush()
        job.user_snapshot = {"id": user.id, "public_keys": ["ssh-ed25519 AAAA alice"]}
        job.request_snapshot = {
            "user_id": user.id,
            "hosts": [{"id": host.id, "name": host.name}],
            "grants": [{"host_id": host.id, "username": "alice", "data_root": "/mnt/old", "data_directory": "/mnt/old/alice"}],
        }
        session.add_all([
            SshPublicKey(managed_user_id=user.id, public_key="ssh-ed25519 AAAA alice", fingerprint="SHA256:alice", comment="alice"),
            HostCredential(host_id=host.id, private_key_ciphertext="cipher", sudo_password_ciphertext="cipher", ssh_verified=True, sudo_verified=True),
        ])
        session.commit()
        monkeypatch.setattr(jobs, "_launch_worker", lambda *_args: (_ for _ in ()).throw(AssertionError("根目录变化时不得执行")))

        with pytest.raises(JobStateError, match="数据根目录已变化"):
            jobs.start_job(session, job, check=False)

        assert session.get(Job, job.id).state == "ready_to_confirm"


def test_adopted_access_grant_execution_accepts_a_snapshot_without_data_root(monkeypatch) -> None:
    with SessionLocal() as session:
        host = Host(name="gpu-adopted-execute", address="192.0.2.35", status="reachable", host_key_fingerprint="SHA256:known")
        user = ManagedUser(username="alice")
        job = Job(
            kind="access_grant_provision",
            state="ready_to_confirm",
            user_snapshot={"id": "placeholder", "public_keys": ["ssh-ed25519 AAAA alice"]},
            request_snapshot={"user_id": "placeholder", "hosts": [], "grants": []},
        )
        session.add_all([host, user, job])
        session.flush()
        job.user_snapshot = {"id": user.id, "public_keys": ["ssh-ed25519 AAAA alice"]}
        job.request_snapshot = {
            "user_id": user.id,
            "hosts": [{"id": host.id, "name": host.name}],
            "grants": [{
                "host_id": host.id,
                "username": "legacy-alice",
                "account_origin": "adopted",
                "data_root": None,
                "data_directory": None,
                "remote_uid": 1007,
                "remote_primary_group": "research",
                "remote_home": "/srv/homes/legacy-alice",
            }],
        }
        session.add_all([
            SshPublicKey(managed_user_id=user.id, public_key="ssh-ed25519 AAAA alice", fingerprint="SHA256:alice", comment="alice"),
            HostCredential(host_id=host.id, private_key_ciphertext="cipher", sudo_password_ciphertext="cipher", ssh_verified=True, sudo_verified=True),
            JobTarget(job_id=job.id, host_id=host.id, state="succeeded"),
        ])
        session.commit()
        monkeypatch.setattr(jobs, "_launch_worker", lambda *_args: jobs.RUNNER_LOCK.release())

        started = jobs.start_job(session, job, check=False)

        assert started.state == "running"


def test_sync_runner_private_data_is_removed_after_persisting_redacted_events(monkeypatch, tmp_path) -> None:
    with SessionLocal() as session:
        host = Host(name="lab-transient", address="192.0.2.23", status="reachable", host_key_fingerprint="SHA256:known")
        user = ManagedUser(username="alice", home="/home/alice")
        session.add_all([host, user])
        session.flush()
        cipher = CredentialCipher.from_settings()
        session.add(HostCredential(host_id=host.id, private_key_ciphertext=cipher.encrypt("private-key"), sudo_password_ciphertext=cipher.encrypt("sudo-secret"), ssh_verified=True, sudo_verified=True))
        job = Job(
            kind="sync",
            state="running",
            user_snapshot={"username": "alice"},
            request_snapshot={"user_id": user.id, "hosts": [{"id": host.id, "name": host.name, "address": host.address, "port": 22, "ssh_user": "ops", "fingerprint": "SHA256:known"}]},
            script_snapshot=None,
        )
        session.add(job)
        session.flush()
        session.add(JobTarget(job_id=job.id, host_id=host.id, state="running"))
        session.commit()
        roots = []

        monkeypatch.setattr(jobs, "_scan_ed25519_key", lambda _host: ("SHA256:known", "lab-transient ssh-ed25519 AAAA", None))

        def fake_run(request, event_handler, key_path):
            roots.append(request.private_data_dir)
            leaked = request.private_data_dir / "env" / "extravars"
            leaked.parent.mkdir()
            leaked.write_text("sudo-secret\nprivate-key", encoding="utf-8")
            event_handler(redact_event({"event": "runner_on_ok", "stdout": "sudo-secret"}, key_path, sensitive_values=request.sensitive_values))
            return RunnerResult(status="successful", rc=0, events=[])

        monkeypatch.setattr(jobs, "run_playbook", fake_run)

        result = jobs._run_job(session, job, check=False)

        assert result.state == "succeeded"
        assert roots and not roots[0].exists()
        assert "sudo-secret" not in "\n".join(event.message for event in session.scalars(select(jobs.JobEvent).where(jobs.JobEvent.job_id == job.id)))
