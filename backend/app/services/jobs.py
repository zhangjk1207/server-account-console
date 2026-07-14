import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Host, Job, JobEvent, JobTarget, ManagedUser, ScriptTemplate, SshPublicKey
from app.services.runner import RunnerRequest, run_playbook

class JobStateError(ValueError):
    pass


def ensure_executable(state: str) -> None:
    if state != "ready_to_confirm":
        raise JobStateError("只有预检完成的任务可以执行")

def utc_now() -> datetime: return datetime.now(timezone.utc)

def create_job(session: Session, user: ManagedUser, hosts: list[Host], script: ScriptTemplate | None) -> Job:
    keys = list(session.scalars(select(SshPublicKey).where(SshPublicKey.managed_user_id == user.id, SshPublicKey.enabled.is_(True))))
    if not keys: raise JobStateError("用户没有启用的 SSH 公钥")
    if any(host.status != "reachable" for host in hosts): raise JobStateError("所有目标机器必须处于可连接状态")
    user_snapshot = {"username": user.username, "primary_group": user.primary_group, "groups": user.groups, "shell": user.shell, "home": user.home, "sudo_rule": user.sudo_rule, "public_keys": [key.public_key for key in keys]}
    request_snapshot = {"user_id": user.id, "host_ids": [host.id for host in hosts], "hosts": [{"id": h.id, "name": h.name, "address": h.address, "port": h.port, "ssh_user": h.ssh_user, "fingerprint": h.host_key_fingerprint} for h in hosts]}
    script_snapshot = None if script is None else {"id": script.id, "name": script.name, "version": script.version, "body": script.body}
    job = Job(kind="sync", state="preview_running", user_snapshot=user_snapshot, request_snapshot=request_snapshot, script_snapshot=script_snapshot, started_at=utc_now())
    session.add(job); session.flush()
    for host in hosts: session.add(JobTarget(job_id=job.id, host_id=host.id, state="pending"))
    session.commit(); return job

def execute_job(session: Session, job: Job, check: bool) -> Job:
    if not check: ensure_executable(job.state)
    job.state = "preview_running" if check else "running"; job.started_at = utc_now(); session.commit()
    artifact = Path("ansible-artifacts") / job.id
    project = artifact / "project"; project.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parents[2] / "ansible"; shutil.copytree(source, project, dirs_exist_ok=True)
    task_input = artifact / "task-input.json"; task_input.write_text(json.dumps(job.request_snapshot), encoding="utf-8")
    post_script = ""
    if job.script_snapshot:
        path = artifact / "post-script.sh"; path.write_text(job.script_snapshot["body"], encoding="utf-8"); path.chmod(0o700); post_script = str(path)
    inventory = {"all": {"hosts": {host["name"]: {"ansible_host": host["address"], "ansible_port": host["port"], "ansible_user": host["ssh_user"], "ansible_ssh_private_key_file": get_settings().control_ssh_key_path} for host in job.request_snapshot["hosts"]}}}
    def event_handler(event: dict) -> None:
        message = str(event.get("stdout", "")); host_name = event.get("event_data", {}).get("host"); host_id = next((h["id"] for h in job.request_snapshot["hosts"] if h["name"] == host_name), None)
        if message: session.add(JobEvent(job_id=job.id, host_id=host_id, level="error" if "failed" in message.lower() else "info", message=message)); session.commit()
    result = run_playbook(RunnerRequest(artifact, inventory, {"desired_user": job.user_snapshot, "post_script_path": post_script, "task_input_path": str(task_input)}, check), event_handler, Path(get_settings().control_ssh_key_path))
    targets = list(session.scalars(select(JobTarget).where(JobTarget.job_id == job.id)))
    for target in targets: target.state = "succeeded" if result.rc == 0 else "failed"; target.finished_at = utc_now()
    job.finished_at = utc_now(); job.state = "ready_to_confirm" if check and result.rc == 0 else ("preview_failed" if check else ("succeeded" if result.rc == 0 else "partial_failed")); session.commit(); session.refresh(job); return job
