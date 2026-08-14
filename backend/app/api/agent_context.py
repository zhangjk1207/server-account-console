from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.models import Host, HostAccessGrant, Job, ManagedUser, SshPublicKey, utc_now
from app.db.session import get_db_session
from app.schemas.agent_context import AgentOverview, GrantOverview, MachineOverview, MemberOverview, RunOverview

router = APIRouter(prefix="/agent-context", tags=["agent-context"], dependencies=[Depends(require_admin)])


@router.get("/overview", response_model=AgentOverview)
def overview(session: Session = Depends(get_db_session)) -> AgentOverview:
    machine_states = dict(
        session.execute(
            select(Host.status, func.count(Host.id)).where(Host.archived.is_(False)).group_by(Host.status)
        ).all()
    )
    machine_total = sum(machine_states.values())
    active_members = session.scalar(select(func.count(ManagedUser.id)).where(ManagedUser.enabled.is_(True))) or 0
    members_with_keys = session.scalar(
        select(func.count(func.distinct(SshPublicKey.managed_user_id)))
        .join(ManagedUser, ManagedUser.id == SshPublicKey.managed_user_id)
        .where(ManagedUser.enabled.is_(True), SshPublicKey.enabled.is_(True))
    ) or 0
    active_grants = session.scalar(
        select(func.count(HostAccessGrant.id)).where(HostAccessGrant.state == "active")
    ) or 0
    active_states = {"pending", "preview_running", "ready_to_confirm", "running"}
    failed_states = {"preview_failed", "partial_failed"}
    active_runs = session.scalar(select(func.count(Job.id)).where(Job.state.in_(active_states))) or 0
    failed_recently = session.scalar(
        select(func.count(Job.id)).where(Job.state.in_(failed_states), Job.created_at >= utc_now() - timedelta(days=7))
    ) or 0

    reachable = machine_states.get("reachable", 0)
    return AgentOverview(
        machines=MachineOverview(total=machine_total, reachable=reachable, attention=machine_total - reachable),
        members=MemberOverview(active=active_members, with_keys=members_with_keys),
        grants=GrantOverview(active=active_grants),
        runs=RunOverview(active=active_runs, failed_recently=failed_recently),
    )
