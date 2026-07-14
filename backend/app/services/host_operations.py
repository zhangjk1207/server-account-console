import json
import os
import shutil
import threading
import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Host, HostCredential, Job, JobTarget, ManagedUser, SshPublicKey
from app.db.session import SessionLocal
from app.schemas.host_operation import HostAuthorizedKeyRead, HostUserOperation, HostUserRead
from app.services.host_connections import decrypt_host_credential
from app.services.hosts import _scan_ed25519_key
from app.services.jobs import (
    RUNNER_LOCK,
    JobStateError,
    _artifact_dir,
    _finish_exception,
    _finish_pending_targets,
    _mark_target_failure,
    _set_started,
    apply_runner_events,
    utc_now,
)
from app.services.runner import RunnerRequest, run_playbook
from app.services.users import parse_public_key


def parse_inventory(facts: dict) -> list[HostUserRead]:
    passwd = facts.get("getent_passwd")
    groups = facts.get("getent_group")
    if not isinstance(passwd, dict) or not isinstance(groups, dict):
        raise ValueError("主机用户盘点结果无效")
    result: list[HostUserRead] = []
    for username, fields in passwd.items():
        if not isinstance(fields, list) or len(fields) < 6:
            continue
        try:
            uid = int(fields[1])
        except (TypeError, ValueError):
            continue
        if uid < 1000:
            continue
        memberships = sorted(
            group_name
            for group_name, group_fields in groups.items()
            if isinstance(group_fields, list) and len(group_fields) >= 3 and username in str(group_fields[2]).split(",")
        )
        result.append(
            HostUserRead(
                username=username,
                uid=uid,
                primary_group=str(fields[2]),
                groups=memberships,
                shell=str(fields[5]),
                home=str(fields[4]),
                locked=None,
                expires_at=None,
            )
        )
    return sorted(result, key=lambda user: user.username)


def require_verified_host_credential(session: Session, host: Host) -> HostCredential:
    credential = session.query(HostCredential).filter(HostCredential.host_id == host.id).one_or_none()
    if credential is None or credential.ssh_verified is not True or credential.sudo_verified is not True:
        raise JobStateError("连接凭证尚未通过 SSH 和 sudo 验证")
    return credential


def create_host_operation_preview(session: Session, host: Host, operation: HostUserOperation) -> Job:
    require_verified_host_credential(session, host)
    if host.status != "reachable":
        raise JobStateError("机器当前不可连接")
    operation = expand_managed_person(session, operation)
    request_snapshot = {
        "host_ids": [host.id],
        "hosts": [{"id": host.id, "name": host.name, "address": host.address, "port": host.port, "ssh_user": host.ssh_user, "fingerprint": host.host_key_fingerprint}],
        "operation": operation.model_dump(exclude_none=True),
    }
    job = Job(kind="host_user_operation", state="pending", user_snapshot={}, request_snapshot=request_snapshot, script_snapshot=None)
    session.add(job)
    session.flush()
    session.add(JobTarget(job_id=job.id, host_id=host.id, state="pending"))
    session.commit()
    session.refresh(job)
    return job


def expand_managed_person(session: Session, operation: HostUserOperation) -> HostUserOperation:
    if operation.managed_user_id is None:
        return operation
    user = session.get(ManagedUser, operation.managed_user_id)
    if user is None or not user.enabled:
        raise JobStateError("受管人员不存在或已停用")
    if user.username != operation.username:
        raise JobStateError("受管人员与目标用户名不一致")
    values = operation.model_dump(exclude_none=True)
    values.setdefault("primary_group", user.primary_group)
    values.setdefault("groups", user.groups)
    values.setdefault("shell", user.shell)
    values.setdefault("home", user.home)
    values.setdefault("sudo_rule", user.sudo_rule)
    if operation.action == "upsert" and "public_keys" not in values:
        values["public_keys"] = list(
            session.scalars(
                select(SshPublicKey.public_key).where(
                    SshPublicKey.managed_user_id == user.id,
                    SshPublicKey.enabled.is_(True),
                )
            )
        )
    return HostUserOperation.model_validate(values)


def list_host_users(session: Session, host: Host) -> list[HostUserRead]:
    require_verified_host_credential(session, host)
    if not RUNNER_LOCK.acquire(blocking=False):
        raise JobStateError("已有任务正在运行")
    try:
        result = _run_user_inventory(session, host)
    finally:
        RUNNER_LOCK.release()
    if result.rc != 0:
        raise JobStateError("读取主机用户失败")
    for event in reversed(result.events):
        data = event.get("event_data") if isinstance(event.get("event_data"), dict) else {}
        result_data = data.get("res") if isinstance(data.get("res"), dict) else {}
        message = result_data.get("msg")
        if isinstance(message, dict) and "getent_passwd" in message:
            return parse_inventory(message)
    raise JobStateError("主机用户盘点结果无效")


def _run_user_inventory(session: Session, host: Host):
    return _run_inspection(session, host, {"action": "inspect"})


def list_host_user_keys(session: Session, host: Host, username: str) -> list[HostAuthorizedKeyRead]:
    require_verified_host_credential(session, host)
    if not RUNNER_LOCK.acquire(blocking=False):
        raise JobStateError("已有任务正在运行")
    try:
        result = _run_key_inventory(session, host, username)
    finally:
        RUNNER_LOCK.release()
    if result.rc != 0:
        raise JobStateError("读取用户公钥失败")
    for event in reversed(result.events):
        data = event.get("event_data") if isinstance(event.get("event_data"), dict) else {}
        result_data = data.get("res") if isinstance(data.get("res"), dict) else {}
        message = result_data.get("msg")
        if isinstance(message, dict) and isinstance(message.get("authorized_keys"), str):
            keys: list[HostAuthorizedKeyRead] = []
            for line in message["authorized_keys"].splitlines():
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                try:
                    public_key, fingerprint, comment = parse_public_key(line)
                except ValueError:
                    continue
                keys.append(HostAuthorizedKeyRead(public_key=public_key, fingerprint=fingerprint, comment=comment))
            return keys
    raise JobStateError("主机公钥盘点结果无效")


def _run_key_inventory(session: Session, host: Host, username: str):
    return _run_inspection(session, host, {"action": "inspect_keys", "username": username})


def _run_inspection(session: Session, host: Host, operation: dict):
    with tempfile.TemporaryDirectory(prefix="host-inventory-") as temporary_directory:
        artifact = Path(temporary_directory)
        project = artifact / "project"
        shutil.copytree(Path(__file__).resolve().parents[2] / "ansible", project)
        fingerprint, known_line, error = _scan_ed25519_key(host)
        if error or known_line is None or fingerprint != host.host_key_fingerprint:
            raise JobStateError("主机指纹校验失败")
        credential = decrypt_host_credential(session, host)
        credentials_dir = artifact / "credentials"
        credentials_dir.mkdir()
        key_path = credentials_dir / f"{host.id}.key"
        key_path.write_text(credential.private_key, encoding="utf-8")
        os.chmod(key_path, 0o600)
        known_hosts = artifact / "known_hosts"
        known_hosts.write_text(f"{known_line}\n", encoding="utf-8")
        inventory = {
            "all": {
                "hosts": {
                    host.name: {
                        "ansible_host": host.address,
                        "ansible_port": host.port,
                        "ansible_user": host.ssh_user,
                        "ansible_ssh_private_key_file": str(key_path),
                        "ansible_ssh_common_args": f"-o UserKnownHostsFile={known_hosts} -o StrictHostKeyChecking=yes -o ConnectTimeout=10",
                        "ansible_ssh_timeout": 300,
                        "ansible_become": True,
                        "ansible_become_password": credential.sudo_password,
                    }
                }
            }
        }
        try:
            return run_playbook(
                RunnerRequest(
                    artifact,
                    inventory,
                    {"host_operation": operation},
                    False,
                    playbook="host_operations.yml",
                    sensitive_values=(credential.private_key, credential.sudo_password),
                ),
                lambda _event: None,
                credentials_dir,
            )
        finally:
            key_path.unlink(missing_ok=True)


def create_and_start_host_operation(session: Session, host: Host, operation: HostUserOperation) -> Job:
    if not RUNNER_LOCK.acquire(blocking=False):
        raise JobStateError("已有任务正在运行")
    try:
        job = create_host_operation_preview(session, host, operation)
        _set_started(session, job, check=True)
    except Exception:
        RUNNER_LOCK.release()
        raise
    _launch_operation_worker(job.id, True)
    session.refresh(job)
    return job


def execute_host_operation(session: Session, job: Job, *, new_password: str | None = None) -> Job:
    if job.kind != "host_user_operation":
        raise JobStateError("任务不是主机用户运维任务")
    operation = job.request_snapshot.get("operation")
    if not isinstance(operation, dict):
        raise JobStateError("任务操作参数无效")
    if operation.get("action") == "reset_password" and not new_password:
        raise JobStateError("重置密码需要输入新密码")
    if not RUNNER_LOCK.acquire(blocking=False):
        raise JobStateError("已有任务正在运行")
    try:
        _set_started(session, job, check=False)
    except Exception:
        RUNNER_LOCK.release()
        raise
    _launch_operation_worker(job.id, False, new_password)
    session.refresh(job)
    return job


def _launch_operation_worker(job_id: str, check: bool, new_password: str | None = None) -> None:
    worker = threading.Thread(target=_run_operation_worker, args=(job_id, check, new_password), daemon=True, name=f"host-operation-{job_id}")
    worker.start()


def _run_operation_worker(job_id: str, check: bool, new_password: str | None = None) -> None:
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        if job is None:
            RUNNER_LOCK.release()
            return
        try:
            _run_host_operation_job(session, job, check, new_password)
        except JobStateError as error:
            _finish_exception(session, job, check, error)
        except Exception as error:
            _finish_exception(session, job, check, JobStateError(f"任务执行异常：{error}"))
        finally:
            RUNNER_LOCK.release()


def _run_host_operation_job(session: Session, job: Job, check: bool, new_password: str | None = None) -> Job:
    artifact = _artifact_dir(job.id)
    project = artifact / "project"
    project.mkdir(parents=True, exist_ok=True)
    shutil.copytree(Path(__file__).resolve().parents[2] / "ansible", project, dirs_exist_ok=True)
    host_data = job.request_snapshot["hosts"][0]
    connection_host = Host(name=host_data["name"], address=host_data["address"], port=host_data["port"], ssh_user=host_data["ssh_user"])
    fingerprint, known_line, error = _scan_ed25519_key(connection_host)
    if error or known_line is None or fingerprint != host_data["fingerprint"]:
        _mark_target_failure(session, job, host_data["id"], f"主机 {host_data['name']} 的指纹校验失败")
        session.commit()
        raise JobStateError("没有通过主机指纹校验的目标机器")
    stored_host = session.get(Host, host_data["id"])
    if stored_host is None:
        raise JobStateError("主机不存在")
    credential = decrypt_host_credential(session, stored_host)
    credentials_dir = artifact / "credentials"
    credentials_dir.mkdir(parents=True, exist_ok=True)
    key_path = credentials_dir / f"{stored_host.id}.key"
    key_path.write_text(credential.private_key, encoding="utf-8")
    os.chmod(key_path, 0o600)
    known_hosts = artifact / "known_hosts"
    known_hosts.write_text(f"{known_line}\n", encoding="utf-8")
    inventory = {
        "all": {
            "hosts": {
                host_data["name"]: {
                    "ansible_host": host_data["address"],
                    "ansible_port": host_data["port"],
                    "ansible_user": host_data["ssh_user"],
                    "ansible_ssh_private_key_file": str(key_path),
                    "ansible_ssh_common_args": f"-o UserKnownHostsFile={known_hosts} -o StrictHostKeyChecking=yes -o ConnectTimeout=10",
                    "ansible_ssh_timeout": 300,
                    "ansible_become": True,
                    "ansible_become_password": credential.sudo_password,
                }
            }
        }
    }

    def event_handler(event: dict) -> None:
        apply_runner_events(session, job, [event])

    try:
        operation = dict(job.request_snapshot["operation"])
        sensitive_values = [credential.private_key, credential.sudo_password]
        if operation.get("action") == "reset_password":
            if not new_password:
                raise JobStateError("重置密码需要输入新密码")
            operation["new_password"] = f"{operation['username']}:{new_password}"
            sensitive_values.extend([new_password, operation["new_password"]])
        result = run_playbook(
            RunnerRequest(
                artifact,
                inventory,
                {"host_operation": operation, "host_operation_new_password": operation.pop("new_password", "")},
                check,
                playbook="host_operations.yml",
                sensitive_values=tuple(sensitive_values),
            ),
            event_handler,
            credentials_dir,
        )
    finally:
        key_path.unlink(missing_ok=True)
        credentials_dir.rmdir()
    failure_message = "Ansible 以非零状态退出，未收到该机器的具体失败事件" if result.rc != 0 else None
    targets = _finish_pending_targets(session, job, failure_message=failure_message)
    failed = any(target.state == "failed" for target in targets)
    job.finished_at = utc_now()
    job.state = "preview_failed" if check and (failed or result.rc != 0) else "ready_to_confirm" if check else "partial_failed" if failed or result.rc != 0 else "succeeded"
    session.commit()
    session.refresh(job)
    return job
