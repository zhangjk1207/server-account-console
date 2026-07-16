from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import require_admin, require_csrf
from app.db.models import Host, HostAccessGrant, HostCredential, Job, JobTarget
from app.db.session import get_db_session
from app.schemas.host import FingerprintConfirmation, HostCreate, HostProbeRead, HostRead, HostUpdate
from app.services.hosts import _scan_ed25519_key, apply_probe_result, create_host, get_active_host, probe_host, update_host
from app.services.host_connections import apply_credential_probe, test_host_credential

router = APIRouter(prefix="/hosts", tags=["hosts"], dependencies=[Depends(require_admin)])


def require_host(session: Session, host_id: str) -> Host:
    host = get_active_host(session, host_id)
    if host is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="机器不存在")
    return host


@router.get("", response_model=list[HostRead])
def list_hosts(session: Session = Depends(get_db_session)) -> list[Host]:
    return list(session.scalars(select(Host).where(Host.archived.is_(False)).order_by(Host.name)))


@router.post("", response_model=HostRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
def add_host(payload: HostCreate, session: Session = Depends(get_db_session)) -> Host:
    try:
        return create_host(session, payload)
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="机器名称已存在") from error


@router.patch("/{host_id}", response_model=HostRead, dependencies=[Depends(require_csrf)])
def edit_host(host_id: str, payload: HostUpdate, session: Session = Depends(get_db_session)) -> Host:
    host = require_host(session, host_id)
    if "data_root" in payload.model_fields_set and payload.data_root != host.data_root:
        active_grant = session.scalar(select(HostAccessGrant.id).where(HostAccessGrant.host_id == host.id, HostAccessGrant.state == "active"))
        if active_grant is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="机器存在活跃授权，不能修改数据根目录")
    return update_host(session, host, payload)


@router.delete("/{host_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)])
def archive_host(host_id: str, session: Session = Depends(get_db_session)) -> Response:
    host = require_host(session, host_id)
    active_target = session.scalar(
        select(JobTarget.id).join(Job, Job.id == JobTarget.job_id).where(
            JobTarget.host_id == host.id,
            Job.state.in_({"pending", "preview_running", "ready_to_confirm", "running"}),
        )
    )
    if active_target is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="机器被未完成任务引用，暂不能归档")
    host.archived = True
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{host_id}/test", response_model=HostProbeRead, dependencies=[Depends(require_csrf)])
def test_host(host_id: str, session: Session = Depends(get_db_session)) -> HostProbeRead:
    host = require_host(session, host_id)
    credential = session.query(HostCredential).filter(HostCredential.host_id == host.id).one_or_none()
    if credential is not None:
        result = test_host_credential(session, host)
        apply_credential_probe(session, host, result)
        reachable = result.ssh_ok is True
        requires_confirmation = result.requires_confirmation
    else:
        result = probe_host(host)
        apply_probe_result(host, result)
        reachable = result.reachable
        requires_confirmation = host.status == "unconfirmed" and result.fingerprint is not None
    session.commit()
    return HostProbeRead(
        status=host.status,
        fingerprint=result.fingerprint,
        reachable=reachable,
        latency_ms=result.latency_ms,
        error=result.error,
        requires_confirmation=requires_confirmation,
    )


@router.post("/{host_id}/confirm-fingerprint", response_model=HostRead, dependencies=[Depends(require_csrf)])
def confirm_fingerprint(host_id: str, payload: FingerprintConfirmation, session: Session = Depends(get_db_session)) -> Host:
    host = require_host(session, host_id)
    fingerprint, _, error = _scan_ed25519_key(host)
    if error or fingerprint != payload.fingerprint:
        host.status = "fingerprint_changed"
        host.last_probe_error = error or "确认时检测到主机指纹变化"
        session.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="主机指纹已变化，请重新测试连接")
    host.host_key_fingerprint = payload.fingerprint
    if session.query(HostCredential).filter(HostCredential.host_id == host.id).one_or_none() is not None:
        apply_credential_probe(session, host, test_host_credential(session, host))
    else:
        apply_probe_result(host, probe_host(host))
    session.commit()
    session.refresh(host)
    return host
