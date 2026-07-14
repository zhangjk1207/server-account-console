from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.jobs import require_job, serialize_job
from app.core.security import require_admin, require_csrf
from app.db.models import Host
from app.db.session import get_db_session
from app.schemas.host_operation import HostAuthorizedKeyRead, HostOperationExecute, SshPasswordAuthenticationPreview, SshPasswordAuthenticationRead, HostUserOperation, HostUserRead
from app.schemas.job import JobRead
from app.services.host_operations import create_and_start_host_operation, create_ssh_password_authentication_preview, execute_host_operation, get_ssh_password_authentication, list_host_user_keys, list_host_users
from app.services.jobs import JobStateError


router = APIRouter(prefix="/hosts", tags=["host-operations"], dependencies=[Depends(require_admin)])
execution_router = APIRouter(prefix="/host-operations", tags=["host-operations"], dependencies=[Depends(require_admin)])


def require_host(session: Session, host_id: str) -> Host:
    host = session.get(Host, host_id)
    if host is None or host.archived:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="机器不存在")
    return host


@router.get("/{host_id}/users", response_model=list[HostUserRead])
def get_host_users(host_id: str, session: Session = Depends(get_db_session)) -> list[HostUserRead]:
    try:
        return list_host_users(session, require_host(session, host_id))
    except JobStateError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error


@router.get("/{host_id}/users/{username}/keys", response_model=list[HostAuthorizedKeyRead])
def get_host_user_keys(host_id: str, username: str, session: Session = Depends(get_db_session)) -> list[HostAuthorizedKeyRead]:
    try:
        return list_host_user_keys(session, require_host(session, host_id), username)
    except JobStateError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error


@router.get("/{host_id}/ssh-password-authentication", response_model=SshPasswordAuthenticationRead)
def get_password_authentication(host_id: str, session: Session = Depends(get_db_session)) -> SshPasswordAuthenticationRead:
    try:
        return get_ssh_password_authentication(session, require_host(session, host_id))
    except JobStateError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error


@router.post("/{host_id}/ssh-password-authentication/preview", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_csrf)])
def preview_password_authentication(
    host_id: str,
    payload: SshPasswordAuthenticationPreview,
    session: Session = Depends(get_db_session),
) -> JobRead:
    try:
        return serialize_job(session, create_ssh_password_authentication_preview(session, require_host(session, host_id), payload))
    except JobStateError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error


@router.post("/{host_id}/user-operations/preview", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_csrf)])
def preview_user_operation(
    host_id: str,
    payload: HostUserOperation,
    session: Session = Depends(get_db_session),
) -> JobRead:
    try:
        return serialize_job(session, create_and_start_host_operation(session, require_host(session, host_id), payload))
    except JobStateError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error


@execution_router.post("/{job_id}/execute", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_csrf)])
def execute_user_operation(
    job_id: str,
    payload: HostOperationExecute,
    session: Session = Depends(get_db_session),
) -> JobRead:
    try:
        return serialize_job(session, execute_host_operation(session, require_job(session, job_id), new_password=payload.new_password))
    except JobStateError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
