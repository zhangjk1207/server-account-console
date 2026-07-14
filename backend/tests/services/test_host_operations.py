from cryptography.fernet import Fernet
import pytest

from app.core.config import get_settings
from app.db.models import Host, HostCredential, Job, ManagedUser, SshPublicKey
from app.db.session import SessionLocal
from app.schemas.host_operation import HostUserOperation, SshPasswordAuthenticationPreview
from app.services import host_operations
from app.services.credentials import CredentialCipher
from app.services.host_operations import (
    create_and_start_host_operation,
    create_host_operation_preview,
    create_ssh_password_authentication_preview,
    execute_host_operation,
    get_ssh_password_authentication,
    list_host_user_keys,
    list_host_users,
    parse_inventory,
)
from app.services.jobs import JobStateError, RUNNER_LOCK
from app.services.runner import RunnerResult


def add_verified_credential(session, host: Host) -> None:
    cipher = CredentialCipher.from_settings()
    session.add(
        HostCredential(
            host_id=host.id,
            private_key_ciphertext=cipher.encrypt("private"),
            sudo_password_ciphertext=cipher.encrypt("sudo"),
            ssh_verified=True,
            sudo_verified=True,
        )
    )
    session.commit()


def test_parse_inventory_filters_system_users_and_never_exposes_shadow() -> None:
    users = parse_inventory(
        {
            "getent_passwd": {
                "daemon": ["x", "1", "1", "daemon", "/usr/sbin", "/usr/sbin/nologin"],
                "alice": ["x", "1001", "1001", "Alice", "/home/alice", "/bin/bash"],
            },
            "getent_group": {"alice": ["x", "1001", ""], "developers": ["x", "1002", "alice"]},
        }
    )

    assert len(users) == 1
    assert users[0].username == "alice"
    assert users[0].uid == 1001
    assert users[0].primary_group == "alice"
    assert users[0].groups == ["developers"]
    assert "password" not in users[0].model_dump()
    assert "shadow" not in users[0].model_dump()


def test_preview_snapshot_excludes_one_time_password(monkeypatch) -> None:
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    try:
        with SessionLocal() as session:
            host = Host(name="lab-01", address="192.0.2.10", status="reachable")
            session.add(host)
            session.flush()
            add_verified_credential(session, host)

            job = create_host_operation_preview(session, host, HostUserOperation(action="reset_password", username="alice"))

            assert job.kind == "host_user_operation"
            assert job.request_snapshot["operation"] == {"action": "reset_password", "username": "alice", "remove_home": False}
            assert "new_password" not in str(job.request_snapshot)
    finally:
        get_settings.cache_clear()


def test_host_operation_preview_starts_a_background_preflight(monkeypatch) -> None:
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    try:
        with SessionLocal() as session:
            host = Host(name="lab-02", address="192.0.2.11", status="reachable")
            session.add(host)
            session.flush()
            add_verified_credential(session, host)
            launched: list[tuple[str, bool]] = []
            monkeypatch.setattr(host_operations, "_launch_operation_worker", lambda job_id, check: launched.append((job_id, check)))

            job = create_and_start_host_operation(session, host, HostUserOperation(action="lock", username="alice"))

            assert job.state == "preview_running"
            assert launched == [(job.id, True)]
            if RUNNER_LOCK.locked():
                RUNNER_LOCK.release()
    finally:
        get_settings.cache_clear()


def test_list_host_users_parses_fixed_playbook_debug_result(monkeypatch) -> None:
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    try:
        with SessionLocal() as session:
            host = Host(name="lab-03", address="192.0.2.12", status="reachable", host_key_fingerprint="SHA256:known")
            session.add(host)
            session.flush()
            add_verified_credential(session, host)
            monkeypatch.setattr(
                host_operations,
                "_run_user_inventory",
                lambda _session, _host: RunnerResult(
                    status="successful",
                    rc=0,
                    events=[{"event_data": {"res": {"msg": {"getent_passwd": {"alice": ["x", "1001", "1001", "", "/home/alice", "/bin/bash"]}, "getent_group": {}}}}}],
                ),
            )

            assert [user.username for user in list_host_users(session, host)] == ["alice"]
    finally:
        get_settings.cache_clear()


def test_password_reset_execution_keeps_new_password_out_of_job_snapshot(monkeypatch) -> None:
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    try:
        with SessionLocal() as session:
            host = Host(name="lab-reset", address="192.0.2.20", status="reachable")
            session.add(host)
            session.flush()
            add_verified_credential(session, host)
            job = Job(
                kind="host_user_operation",
                state="ready_to_confirm",
                request_snapshot={"hosts": [{"id": host.id}], "operation": {"action": "reset_password", "username": "alice"}},
            )
            session.add(job)
            session.commit()
            launched: list[tuple[str, bool, str | None]] = []
            monkeypatch.setattr(host_operations, "_launch_operation_worker", lambda job_id, check, new_password=None: launched.append((job_id, check, new_password)))

            result = execute_host_operation(session, job, new_password="one-time-secret")

            assert result.state == "running"
            assert "one-time-secret" not in str(result.request_snapshot)
            assert launched == [(job.id, False, "one-time-secret")]
            if RUNNER_LOCK.locked():
                RUNNER_LOCK.release()
    finally:
        get_settings.cache_clear()


def test_host_operation_execution_rechecks_current_host_credential(monkeypatch) -> None:
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    try:
        with SessionLocal() as session:
            host = Host(name="lab-stale", address="192.0.2.22", status="reachable")
            session.add(host)
            session.flush()
            add_verified_credential(session, host)
            credential = session.query(HostCredential).filter(HostCredential.host_id == host.id).one()
            credential.sudo_verified = False
            job = Job(
                kind="host_user_operation",
                state="ready_to_confirm",
                request_snapshot={"hosts": [{"id": host.id}], "operation": {"action": "lock", "username": "alice"}},
            )
            session.add(job)
            session.commit()
            monkeypatch.setattr(host_operations, "_launch_operation_worker", lambda *_args: (_ for _ in ()).throw(AssertionError("凭证失效时不得执行")))

            with pytest.raises(JobStateError, match="连接凭证尚未通过 SSH 和 sudo 验证"):
                execute_host_operation(session, job)

            assert session.get(Job, job.id).state == "ready_to_confirm"
    finally:
        get_settings.cache_clear()


def test_list_host_user_keys_parses_public_keys(monkeypatch) -> None:
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    try:
        with SessionLocal() as session:
            host = Host(name="lab-04", address="192.0.2.13", status="reachable", host_key_fingerprint="SHA256:known")
            session.add(host)
            session.flush()
            add_verified_credential(session, host)
            monkeypatch.setattr(
                host_operations,
                "_run_key_inventory",
                lambda _session, _host, _username: RunnerResult(
                    status="successful",
                    rc=0,
                    events=[{"event_data": {"res": {"msg": {"authorized_keys": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAGkvVkSy22CofC/G8JlQVqBe1HMv/b8MWBNkdQ1spaR alice@laptop\n"}}}}],
                ),
            )

            keys = list_host_user_keys(session, host, "alice")

            assert keys[0].comment == "alice@laptop"
            assert keys[0].fingerprint.startswith("SHA256:")
    finally:
        get_settings.cache_clear()


def test_managed_person_operation_expands_profile_and_enabled_public_keys(monkeypatch) -> None:
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    try:
        with SessionLocal() as session:
            host = Host(name="lab-05", address="192.0.2.14", status="reachable")
            user = ManagedUser(username="alice", primary_group="developers", groups=["docker"], shell="/bin/zsh", home="/srv/alice", sudo_rule="ALL=(ALL) NOPASSWD:ALL")
            session.add_all([host, user])
            session.flush()
            add_verified_credential(session, host)
            session.add_all([
                SshPublicKey(managed_user_id=user.id, public_key="ssh-ed25519 AAAA enabled", fingerprint="SHA256:enabled", comment="enabled", enabled=True),
                SshPublicKey(managed_user_id=user.id, public_key="ssh-ed25519 AAAA disabled", fingerprint="SHA256:disabled", comment="disabled", enabled=False),
            ])
            session.commit()

            job = create_host_operation_preview(session, host, HostUserOperation(action="upsert", username="alice", managed_user_id=user.id))

            operation = job.request_snapshot["operation"]
            assert operation["primary_group"] == "developers"
            assert operation["groups"] == ["docker"]
            assert operation["shell"] == "/bin/zsh"
            assert operation["home"] == "/srv/alice"
            assert operation["public_keys"] == ["ssh-ed25519 AAAA enabled"]
    finally:
        get_settings.cache_clear()


def test_ssh_password_authentication_preview_captures_target_state(monkeypatch) -> None:
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    try:
        with SessionLocal() as session:
            host = Host(name="lab-06", address="192.0.2.15", status="reachable")
            session.add(host)
            session.flush()
            add_verified_credential(session, host)
            monkeypatch.setattr(host_operations, "_launch_operation_worker", lambda *_args: None)

            job = create_ssh_password_authentication_preview(session, host, SshPasswordAuthenticationPreview(enabled=False))

            assert job.kind == "ssh_password_authentication"
            assert job.request_snapshot["operation"] == {"action": "sshd_password_authentication", "enabled": False}
            if RUNNER_LOCK.locked():
                RUNNER_LOCK.release()
    finally:
        get_settings.cache_clear()


def test_ssh_password_authentication_parser_reads_effective_value(monkeypatch) -> None:
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    try:
        with SessionLocal() as session:
            host = Host(name="lab-07", address="192.0.2.16", status="reachable", host_key_fingerprint="SHA256:known")
            session.add(host)
            session.flush()
            add_verified_credential(session, host)
            monkeypatch.setattr(
                host_operations,
                "_run_sshd_inspection",
                lambda _session, _host: RunnerResult(status="successful", rc=0, events=[{"event_data": {"res": {"msg": {"password_authentication": False}}}}]),
            )

            assert get_ssh_password_authentication(session, host).enabled is False
    finally:
        get_settings.cache_clear()
