import hashlib
import json
import shutil
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Host, HostUserState, Job, JobEvent, JobTarget, ManagedUser, ScriptTemplate, SshPublicKey
from app.db.session import SessionLocal
from app.services.hosts import _scan_ed25519_key
from app.services.runner import RunnerRequest, run_playbook

RUNNER_LOCK = threading.Lock()
TERMINAL_STATES = {"succeeded", "partial_failed", "preview_failed", "ready_to_confirm", "expired"}


class JobStateError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_executable(state: str) -> None:
    if state != "ready_to_confirm":
        raise JobStateError("只有预检完成的任务可以执行")


def desired_hash(job: Job) -> str:
    payload = {"user": job.user_snapshot, "script": job.script_snapshot}
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def expire_ready_previews(session: Session, *, now: datetime | None = None) -> int:
    now = now or utc_now()
    cutoff = now - timedelta(minutes=30)
    expired = list(session.scalars(select(Job).where(Job.state == "ready_to_confirm", Job.finished_at < cutoff)))
    for job in expired:
        job.state = "expired"
        session.add(JobEvent(job_id=job.id, host_id=None, level="warning", message="预检已超过 30 分钟，需要重新预检"))
    if expired:
        session.commit()
    return len(expired)


def create_job(session: Session, user: ManagedUser, hosts: list[Host], script: ScriptTemplate | None) -> Job:
    if not user.enabled:
        raise JobStateError("已停用的用户不能同步")
    keys = list(session.scalars(select(SshPublicKey).where(SshPublicKey.managed_user_id == user.id, SshPublicKey.enabled.is_(True))))
    if not keys:
        raise JobStateError("用户没有启用的 SSH 公钥")
    if any(host.status != "reachable" for host in hosts):
        raise JobStateError("所有目标机器必须处于可连接状态")

    user_snapshot = {
        "username": user.username,
        "primary_group": user.primary_group,
        "groups": user.groups,
        "shell": user.shell,
        "home": user.home,
        "sudo_rule": user.sudo_rule,
        "public_keys": [key.public_key for key in keys],
    }
    request_snapshot = {
        "user_id": user.id,
        "host_ids": [host.id for host in hosts],
        "hosts": [
            {
                "id": host.id,
                "name": host.name,
                "address": host.address,
                "port": host.port,
                "ssh_user": host.ssh_user,
                "fingerprint": host.host_key_fingerprint,
            }
            for host in hosts
        ],
    }
    script_snapshot = None if script is None else {
        "id": script.id,
        "name": script.name,
        "version": script.version,
        "body": script.body,
    }
    job = Job(kind="sync", state="pending", user_snapshot=user_snapshot, request_snapshot=request_snapshot, script_snapshot=script_snapshot)
    session.add(job)
    session.flush()
    for host in hosts:
        session.add(JobTarget(job_id=job.id, host_id=host.id, state="pending"))
    session.commit()
    session.refresh(job)
    return job


def _artifact_dir(job_id: str) -> Path:
    database_url = get_settings().database_url
    if database_url.startswith("sqlite:///"):
        return Path(database_url.removeprefix("sqlite:///" )).parent / "ansible-artifacts" / job_id
    return Path("ansible-artifacts") / job_id


def _reset_targets(session: Session, job: Job) -> None:
    for target in session.scalars(select(JobTarget).where(JobTarget.job_id == job.id)):
        target.state = "pending"
        target.output = ""
        target.error = None
        target.started_at = None
        target.finished_at = None


def _set_started(session: Session, job: Job, check: bool) -> None:
    if not check:
        expire_ready_previews(session)
        ensure_executable(job.state)
    job.state = "preview_running" if check else "running"
    job.started_at = utc_now()
    job.finished_at = None
    _reset_targets(session, job)
    session.commit()


def execute_job(session: Session, job: Job, check: bool) -> Job:
    """Synchronous entry point retained for service tests and CLI callers."""
    if not RUNNER_LOCK.acquire(blocking=False):
        raise JobStateError("已有任务正在运行")
    try:
        _set_started(session, job, check)
        return _run_job(session, job, check)
    except JobStateError as error:
        return _finish_exception(session, job, check, error)
    finally:
        RUNNER_LOCK.release()


def start_job(session: Session, job: Job, check: bool) -> Job:
    """Start a job in a background worker while retaining the single runner lock."""
    if not RUNNER_LOCK.acquire(blocking=False):
        raise JobStateError("已有任务正在运行")
    try:
        _set_started(session, job, check)
    except Exception:
        RUNNER_LOCK.release()
        raise

    _launch_worker(job.id, check)
    session.refresh(job)
    return job


def create_and_start_job(
    session: Session,
    user: ManagedUser,
    hosts: list[Host],
    script: ScriptTemplate | None,
    *,
    check: bool,
) -> Job:
    """Acquire the runner before creating a task, so conflicts leave no orphan record."""
    if not RUNNER_LOCK.acquire(blocking=False):
        raise JobStateError("已有任务正在运行")
    try:
        job = create_job(session, user, hosts, script)
        _set_started(session, job, check)
    except Exception:
        RUNNER_LOCK.release()
        raise
    _launch_worker(job.id, check)
    session.refresh(job)
    return job


def _launch_worker(job_id: str, check: bool) -> None:
    worker = threading.Thread(target=_run_background_job, args=(job_id, check), daemon=True, name=f"sync-job-{job_id}")
    worker.start()


def _run_background_job(job_id: str, check: bool) -> None:
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        if job is None:
            RUNNER_LOCK.release()
            return
        try:
            _run_job(session, job, check)
        except JobStateError as error:
            _finish_exception(session, job, check, error)
        except Exception as error:  # Keep an unexpected runner error visible in the task record.
            _finish_exception(session, job, check, JobStateError(f"任务执行异常：{error}"))
        finally:
            RUNNER_LOCK.release()


def _finish_exception(session: Session, job: Job, check: bool, error: JobStateError) -> Job:
    job.finished_at = utc_now()
    job.state = "preview_failed" if check else "partial_failed"
    session.add(JobEvent(job_id=job.id, host_id=None, level="error", message=str(error)))
    session.commit()
    session.refresh(job)
    return job


def _target_for_host(session: Session, job_id: str, host_name: str | None) -> JobTarget | None:
    if not host_name:
        return None
    return session.scalar(
        select(JobTarget)
        .join(Host, Host.id == JobTarget.host_id)
        .where(JobTarget.job_id == job_id, Host.name == host_name)
    )


def _append_output(target: JobTarget, message: str) -> None:
    if not message:
        return
    target.output = f"{target.output}\n{message}".strip()


def apply_runner_events(session: Session, job: Job, events: list[dict]) -> None:
    """Persist normalized runner events and update only the target that emitted a failure."""
    for event in events:
        event_name = str(event.get("event", "runner_event"))
        data = event.get("event_data") if isinstance(event.get("event_data"), dict) else {}
        host_name = data.get("host")
        message = str(event.get("stdout", "")).strip()
        target = _target_for_host(session, job.id, host_name)
        host_id = target.host_id if target else None
        level = "error" if event_name in {"runner_on_failed", "runner_on_unreachable"} else "info"
        session.add(JobEvent(job_id=job.id, host_id=host_id, level=level, message=f"[{event_name}] {message}".strip()))
        if target is None:
            continue
        target.started_at = target.started_at or utc_now()
        _append_output(target, message)
        if event_name in {"runner_on_failed", "runner_on_unreachable"}:
            target.state = "failed"
            target.error = message or "Ansible 任务失败"
            target.finished_at = utc_now()
    session.commit()


def _mark_target_failure(session: Session, job: Job, host_id: str, message: str) -> None:
    target = session.scalar(select(JobTarget).where(JobTarget.job_id == job.id, JobTarget.host_id == host_id))
    if target is None:
        return
    target.state = "failed"
    target.error = message
    target.finished_at = utc_now()
    session.add(JobEvent(job_id=job.id, host_id=host_id, level="error", message=message))


def _finish_pending_targets(session: Session, job: Job) -> list[JobTarget]:
    targets = list(session.scalars(select(JobTarget).where(JobTarget.job_id == job.id)))
    for target in targets:
        if target.state in {"pending", "running"}:
            target.state = "succeeded"
            target.finished_at = utc_now()
    return targets


def finalize_host_user_states(session: Session, job: Job, *, desired_hash: str) -> None:
    user_id = str(job.request_snapshot["user_id"])
    for target in session.scalars(select(JobTarget).where(JobTarget.job_id == job.id, JobTarget.state == "succeeded")):
        state = session.scalar(
            select(HostUserState).where(HostUserState.host_id == target.host_id, HostUserState.managed_user_id == user_id)
        )
        if state is None:
            state = HostUserState(host_id=target.host_id, managed_user_id=user_id)
            session.add(state)
        state.last_success_job_id = job.id
        state.synced_at = utc_now()
        state.desired_hash = desired_hash
    session.commit()


def _run_job(session: Session, job: Job, check: bool) -> Job:
    artifact = _artifact_dir(job.id)
    project = artifact / "project"
    project.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parents[2] / "ansible"
    shutil.copytree(source, project, dirs_exist_ok=True)

    task_input = {
        "job_id": job.id,
        "user": job.user_snapshot,
        "request": job.request_snapshot,
        "script": None if job.script_snapshot is None else {"id": job.script_snapshot["id"], "name": job.script_snapshot["name"], "version": job.script_snapshot["version"]},
    }
    known_lines: list[str] = []
    inventory_hosts: dict[str, dict] = {}
    for host_data in job.request_snapshot["hosts"]:
        host = Host(name=host_data["name"], address=host_data["address"], port=host_data["port"])
        fingerprint, line, error = _scan_ed25519_key(host)
        if error or fingerprint != host_data["fingerprint"] or line is None:
            _mark_target_failure(session, job, host_data["id"], f"主机 {host_data['name']} 的指纹校验失败")
            continue
        known_lines.append(line)
        inventory_hosts[host_data["name"]] = {
            "ansible_host": host_data["address"],
            "ansible_port": host_data["port"],
            "ansible_user": host_data["ssh_user"],
        }
    session.commit()
    if not inventory_hosts:
        raise JobStateError("没有通过主机指纹校验的目标机器")

    known_hosts = artifact / "known_hosts"
    known_hosts.write_text("\n".join(known_lines) + "\n", encoding="utf-8")
    ssh_args = f"-o UserKnownHostsFile={known_hosts} -o StrictHostKeyChecking=yes -o ConnectTimeout=10"
    for values in inventory_hosts.values():
        values["ansible_ssh_private_key_file"] = get_settings().control_ssh_key_path
        values["ansible_ssh_common_args"] = ssh_args
        values["ansible_ssh_timeout"] = 300
    inventory = {"all": {"hosts": inventory_hosts}}

    def event_handler(event: dict) -> None:
        apply_runner_events(session, job, [event])

    result = run_playbook(
        RunnerRequest(
            artifact,
            inventory,
            {
                "desired_user": job.user_snapshot,
                "post_script_content": "" if job.script_snapshot is None else job.script_snapshot["body"],
                "task_input_json": json.dumps(task_input, ensure_ascii=False),
            },
            check,
        ),
        event_handler,
        Path(get_settings().control_ssh_key_path),
    )
    targets = _finish_pending_targets(session, job)
    failed = any(target.state == "failed" for target in targets)
    job.finished_at = utc_now()
    if check:
        job.state = "preview_failed" if failed or result.rc != 0 else "ready_to_confirm"
    else:
        job.state = "partial_failed" if failed or result.rc != 0 else "succeeded"
    session.commit()
    if not check:
        finalize_host_user_states(session, job, desired_hash=desired_hash(job))
    session.refresh(job)
    return job
