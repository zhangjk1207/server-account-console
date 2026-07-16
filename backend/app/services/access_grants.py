from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Host, HostAccessGrant, HostCredential, Job, JobTarget, ManagedUser, PermissionTemplate, SshPublicKey
from app.schemas.access_grant import AccessGrantProvisionRow, AccessGrantRevokeRow
from app.services.jobs import JobStateError
from app.services.users import normalize_groups


def _active_keys(session: Session, user: ManagedUser) -> list[str]:
    if not user.enabled:
        raise JobStateError("已停用的成员不能开通权限")
    keys = list(session.scalars(select(SshPublicKey.public_key).where(SshPublicKey.managed_user_id == user.id, SshPublicKey.enabled.is_(True))))
    if not keys:
        raise JobStateError("成员没有启用的 SSH 公钥")
    return keys


def _require_host_ready(session: Session, host_id: str, *, require_data_root: bool) -> Host:
    host = session.get(Host, host_id)
    if host is None or host.archived:
        raise JobStateError("目标机器不存在或已归档")
    if require_data_root and not host.data_root:
        raise JobStateError(f"机器 {host.name} 尚未配置数据根目录")
    if host.status != "reachable":
        raise JobStateError(f"机器 {host.name} 当前不可连接")
    credential = session.scalar(select(HostCredential).where(HostCredential.host_id == host.id))
    if credential is None or credential.ssh_verified is not True or credential.sudo_verified is not True:
        raise JobStateError(f"机器 {host.name} 的连接凭证尚未通过 SSH 和 sudo 验证")
    return host


def _host_snapshot(host: Host) -> dict:
    return {
        "id": host.id,
        "name": host.name,
        "address": host.address,
        "port": host.port,
        "ssh_user": host.ssh_user,
        "fingerprint": host.host_key_fingerprint,
    }


def _template_values(session: Session, row: AccessGrantProvisionRow) -> tuple[PermissionTemplate | None, list[str], str | None, dict]:
    template = None
    if row.permission_template_id:
        template = session.get(PermissionTemplate, row.permission_template_id)
        if template is None or not template.enabled:
            raise JobStateError("权限模板不存在或已停用")
    groups = normalize_groups(row.groups_override if row.groups_override is not None else ([] if template is None else template.groups))
    sudo_rule = row.sudo_rule_override if row.sudo_rule_override is not None else (None if template is None else template.sudo_rule)
    snapshot = {
        "id": None if template is None else template.id,
        "name": "自定义" if template is None else template.name,
        "groups": groups,
        "sudo_rule": sudo_rule,
    }
    return template, groups, sudo_rule, snapshot


def _user_snapshot(user: ManagedUser, public_keys: list[str]) -> dict:
    return {"id": user.id, "username": user.username, "display_name": user.display_name, "public_keys": public_keys}


def create_access_grant_job(
    session: Session,
    user: ManagedUser,
    rows: list[AccessGrantProvisionRow] | list[AccessGrantRevokeRow],
    *,
    operation: str,
    check: bool,
) -> Job:
    if operation not in {"provision", "revoke"}:
        raise JobStateError("不支持的授权操作")
    public_keys = _active_keys(session, user) if operation == "provision" else []

    snapshots: list[dict] = []
    hosts: list[Host] = []
    seen_host_ids: set[str] = set()
    if operation == "provision":
        for row in rows:
            assert isinstance(row, AccessGrantProvisionRow)
            if row.host_id in seen_host_ids:
                raise JobStateError("同一批次不能重复选择机器")
            seen_host_ids.add(row.host_id)
            host = _require_host_ready(session, row.host_id, require_data_root=True)
            owner = session.scalar(
                select(HostAccessGrant).where(
                    HostAccessGrant.host_id == host.id,
                    HostAccessGrant.username == row.username,
                    HostAccessGrant.state == "active",
                    HostAccessGrant.managed_user_id != user.id,
                )
            )
            if owner is not None:
                raise JobStateError(f"机器 {host.name} 上的用户名 {row.username} 已被另一名成员使用")
            template, groups, sudo_rule, template_snapshot = _template_values(session, row)
            data_root = str(host.data_root).rstrip("/")
            snapshots.append({
                "host_id": host.id,
                "username": row.username,
                "permission_template_id": None if template is None else template.id,
                "template": template_snapshot,
                "groups_override": None if row.groups_override is None else normalize_groups(row.groups_override),
                "sudo_rule_override": row.sudo_rule_override,
                "groups": groups,
                "sudo_rule": sudo_rule,
                "data_root": data_root,
                "data_directory": f"{data_root}/{row.username}",
                "delete_data": False,
            })
            hosts.append(host)
    else:
        grant_ids = [row.grant_id for row in rows]
        if len(set(grant_ids)) != len(grant_ids):
            raise JobStateError("同一批次不能重复选择授权")
        grants = {
            grant.id: grant
            for grant in session.scalars(
                select(HostAccessGrant).where(HostAccessGrant.id.in_(grant_ids), HostAccessGrant.managed_user_id == user.id, HostAccessGrant.state == "active")
            )
        }
        if len(grants) != len(grant_ids):
            raise JobStateError("待回收授权不存在或已失效")
        for row in rows:
            assert isinstance(row, AccessGrantRevokeRow)
            grant = grants[row.grant_id]
            host = _require_host_ready(session, grant.host_id, require_data_root=True)
            snapshots.append({
                "grant_id": grant.id,
                "host_id": host.id,
                "username": grant.username,
                "data_root": host.data_root,
                "data_directory": grant.data_directory,
                "delete_data": row.delete_data,
            })
            hosts.append(host)

    kind = f"access_grant_{operation}"
    job = Job(
        kind=kind,
        state="preview_running" if check else "running",
        user_snapshot=_user_snapshot(user, public_keys),
        request_snapshot={"user_id": user.id, "operation": operation, "hosts": [_host_snapshot(host) for host in hosts], "grants": snapshots},
        script_snapshot=None,
    )
    session.add(job)
    session.flush()
    for host in hosts:
        session.add(JobTarget(job_id=job.id, host_id=host.id, state="pending"))
    session.commit()
    session.refresh(job)
    return job


def create_and_start_access_grant_job(
    session: Session,
    user: ManagedUser,
    rows: list[AccessGrantProvisionRow] | list[AccessGrantRevokeRow],
    *,
    operation: str,
    check: bool,
) -> Job:
    # Keep the one-runner invariant shared with legacy synchronization tasks.
    from app.services import jobs

    if not jobs.RUNNER_LOCK.acquire(blocking=False):
        raise JobStateError("已有任务正在运行")
    try:
        job = create_access_grant_job(session, user, rows, operation=operation, check=check)
    except Exception:
        jobs.RUNNER_LOCK.release()
        raise
    jobs._launch_worker(job.id, check)
    session.refresh(job)
    return job
