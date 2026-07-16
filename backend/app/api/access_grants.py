from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.jobs import require_job, serialize_job
from app.api.users import require_user
from app.core.security import require_admin, require_csrf
from app.db.models import Host, HostAccessGrant, PermissionTemplate
from app.db.session import get_db_session
from app.schemas.access_grant import (
    AccessGrantPreviewRequest,
    AccessGrantRead,
    AccessGrantRevokePreviewRequest,
)
from app.schemas.job import JobRead
from app.services.access_grants import create_access_grant_job, create_and_start_access_grant_job
from app.services.jobs import JobStateError, start_job

router = APIRouter(prefix="/users/{user_id}/access-grants", tags=["access grants"], dependencies=[Depends(require_admin)])
execution_router = APIRouter(prefix="/access-grant-jobs", tags=["access grants"], dependencies=[Depends(require_admin)])


def serialize_grant(grant: HostAccessGrant, host_name: str, template_name: str | None) -> AccessGrantRead:
    template = grant.template_snapshot or {}
    return AccessGrantRead(
        id=grant.id,
        host_id=grant.host_id,
        host_name=host_name,
        username=grant.username,
        permission_template_id=grant.permission_template_id,
        template_name=template_name or template.get("name"),
        groups=template.get("groups", []),
        sudo_rule=template.get("sudo_rule"),
        data_directory=grant.data_directory,
        state=grant.state,
        last_success_job_id=grant.last_success_job_id,
        updated_at=grant.updated_at,
    )


@router.get("", response_model=list[AccessGrantRead])
def list_access_grants(user_id: str, session: Session = Depends(get_db_session)) -> list[AccessGrantRead]:
    require_user(session, user_id)
    rows = session.execute(
        select(HostAccessGrant, Host.name, PermissionTemplate.name)
        .join(Host, Host.id == HostAccessGrant.host_id)
        .outerjoin(PermissionTemplate, PermissionTemplate.id == HostAccessGrant.permission_template_id)
        .where(HostAccessGrant.managed_user_id == user_id)
        .order_by(Host.name)
    )
    return [serialize_grant(grant, host_name, template_name) for grant, host_name, template_name in rows]


@router.post("/preview", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_csrf)])
def preview_provision(user_id: str, payload: AccessGrantPreviewRequest, session: Session = Depends(get_db_session)) -> JobRead:
    try:
        job = create_and_start_access_grant_job(session, require_user(session, user_id), payload.grants, operation="provision", check=True)
        return serialize_job(session, job)
    except JobStateError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error


@router.post("/revoke/preview", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_csrf)])
def preview_revoke(user_id: str, payload: AccessGrantRevokePreviewRequest, session: Session = Depends(get_db_session)) -> JobRead:
    try:
        job = create_and_start_access_grant_job(session, require_user(session, user_id), payload.grants, operation="revoke", check=True)
        return serialize_job(session, job)
    except JobStateError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error


@execution_router.post("/{job_id}/execute", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_csrf)])
def execute_access_grant_job(job_id: str, session: Session = Depends(get_db_session)) -> JobRead:
    job = require_job(session, job_id)
    if not job.kind.startswith("access_grant_"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="不是授权任务")
    try:
        return serialize_job(session, start_job(session, job, check=False))
    except JobStateError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
