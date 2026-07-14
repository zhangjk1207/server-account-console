import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_admin, require_csrf
from app.db.models import Host, Job, JobEvent, JobTarget, ManagedUser, ScriptTemplate
from app.db.session import SessionLocal, get_db_session
from app.schemas.job import JobEventRead, JobRead, JobTargetRead, PreviewRequest
from app.services.jobs import JobStateError, create_and_start_job, expire_ready_previews, start_job

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_admin)])


def require_job(session: Session, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return job


def serialize_job(session: Session, job: Job) -> JobRead:
    rows = session.execute(
        select(JobTarget, Host.name).join(Host, Host.id == JobTarget.host_id).where(JobTarget.job_id == job.id).order_by(Host.name)
    )
    targets = [
        JobTargetRead(
            host_id=target.host_id,
            host_name=host_name,
            state=target.state,
            output=target.output,
            error=target.error,
            started_at=target.started_at,
            finished_at=target.finished_at,
        )
        for target, host_name in rows
    ]
    return JobRead(
        id=job.id,
        kind=job.kind,
        state=job.state,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        user_snapshot=job.user_snapshot,
        request_snapshot=job.request_snapshot,
        script_snapshot=job.script_snapshot,
        targets=targets,
    )


def resolve_preview_input(session: Session, payload: PreviewRequest) -> tuple[ManagedUser, list[Host], ScriptTemplate | None]:
    user = session.get(ManagedUser, payload.user_id)
    hosts_by_id = {host.id: host for host in session.scalars(select(Host).where(Host.id.in_(payload.host_ids), Host.archived.is_(False)))}
    hosts = [hosts_by_id[host_id] for host_id in payload.host_ids if host_id in hosts_by_id]
    if user is None or len(hosts) != len(payload.host_ids) or len(set(payload.host_ids)) != len(payload.host_ids):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="任务输入无效")
    script = None
    if payload.script_template_id:
        script = session.get(ScriptTemplate, payload.script_template_id)
        if script is None or not script.enabled:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="后置脚本不存在或已停用")
    return user, hosts, script


@router.post("/preview", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_csrf)])
def preview(payload: PreviewRequest, session: Session = Depends(get_db_session)) -> JobRead:
    user, hosts, script = resolve_preview_input(session, payload)
    try:
        return serialize_job(session, create_and_start_job(session, user, hosts, script, check=True))
    except JobStateError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/{job_id}/execute", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_csrf)])
def execute(job_id: str, session: Session = Depends(get_db_session)) -> JobRead:
    try:
        expire_ready_previews(session)
        job = start_job(session, require_job(session, job_id), check=False)
        return serialize_job(session, job)
    except JobStateError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/{job_id}/rerun", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_csrf)])
def rerun(job_id: str, session: Session = Depends(get_db_session)) -> JobRead:
    previous = require_job(session, job_id)
    payload = PreviewRequest(
        user_id=str(previous.request_snapshot["user_id"]),
        host_ids=[str(host_id) for host_id in previous.request_snapshot["host_ids"]],
        script_template_id=None if previous.script_snapshot is None else str(previous.script_snapshot["id"]),
    )
    user, hosts, script = resolve_preview_input(session, payload)
    try:
        return serialize_job(session, create_and_start_job(session, user, hosts, script, check=True))
    except JobStateError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get("", response_model=list[JobRead])
def list_jobs(session: Session = Depends(get_db_session)) -> list[JobRead]:
    expire_ready_previews(session)
    return [serialize_job(session, job) for job in session.scalars(select(Job).order_by(Job.created_at.desc()))]


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: str, session: Session = Depends(get_db_session)) -> JobRead:
    expire_ready_previews(session)
    return serialize_job(session, require_job(session, job_id))


@router.get("/{job_id}/events")
async def events(job_id: str, session: Session = Depends(get_db_session)):
    require_job(session, job_id)

    async def stream():
        sent = 0
        while True:
            with SessionLocal() as event_session:
                rows = list(event_session.scalars(select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.created_at, JobEvent.id)))
                for event in rows[sent:]:
                    payload = JobEventRead(
                        id=event.id,
                        job_id=event.job_id,
                        host_id=event.host_id,
                        level=event.level,
                        message=event.message,
                        created_at=event.created_at,
                    ).model_dump(mode="json")
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                sent = len(rows)
                job = event_session.get(Job, job_id)
                if job is None or job.state in {"succeeded", "partial_failed", "preview_failed", "ready_to_confirm", "expired"}:
                    break
            await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream")
