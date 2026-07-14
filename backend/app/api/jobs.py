import asyncio, json
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.security import require_admin, require_csrf
from app.db.models import Host, Job, JobEvent, ManagedUser, ScriptTemplate
from app.db.session import get_db_session
from app.schemas.job import JobEventRead, JobRead, PreviewRequest
from app.services.jobs import JobStateError, create_job, execute_job

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_admin)])
def require_job(session: Session, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if job is None: raise HTTPException(404, "任务不存在")
    return job
@router.post("/preview", response_model=JobRead, dependencies=[Depends(require_csrf)])
def preview(payload: PreviewRequest, session: Session = Depends(get_db_session)):
    user=session.get(ManagedUser,payload.user_id); hosts=list(session.scalars(select(Host).where(Host.id.in_(payload.host_ids),Host.archived.is_(False)))); script=None if not payload.script_template_id else session.get(ScriptTemplate,payload.script_template_id)
    if user is None or len(hosts)!=len(set(payload.host_ids)) or (script is not None and not script.enabled): raise HTTPException(422,"任务输入无效")
    try: return execute_job(session,create_job(session,user,hosts,script),True)
    except JobStateError as error: raise HTTPException(422,str(error)) from error
@router.post("/{job_id}/execute", response_model=JobRead, dependencies=[Depends(require_csrf)])
def execute(job_id: str, session: Session = Depends(get_db_session)):
    try: return execute_job(session,require_job(session,job_id),False)
    except JobStateError as error: raise HTTPException(409,str(error)) from error
@router.get("",response_model=list[JobRead])
def list_jobs(session: Session=Depends(get_db_session)): return list(session.scalars(select(Job).order_by(Job.created_at.desc())))
@router.get("/{job_id}",response_model=JobRead)
def get_job(job_id: str,session: Session=Depends(get_db_session)): return require_job(session,job_id)
@router.get("/{job_id}/events")
async def events(job_id: str, session: Session=Depends(get_db_session)):
    require_job(session,job_id)
    async def stream():
        sent=0
        while True:
            rows=list(session.scalars(select(JobEvent).where(JobEvent.job_id==job_id).order_by(JobEvent.created_at)))
            for event in rows[sent:]: yield f"data: {json.dumps(JobEventRead.model_validate(event).model_dump(mode='json'))}\n\n"; sent+=1
            job=session.get(Job,job_id)
            if job and job.state in {"succeeded","partial_failed","preview_failed","ready_to_confirm"}: break
            await asyncio.sleep(0.5)
    return StreamingResponse(stream(),media_type="text/event-stream")
