from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import require_admin, require_csrf
from app.db.models import ScriptTemplate
from app.db.session import get_db_session
from app.schemas.script import ScriptTemplateCreate, ScriptTemplateRead, ScriptTemplateUpdate

router = APIRouter(prefix="/script-templates", tags=["scripts"], dependencies=[Depends(require_admin)])


def require_template(session: Session, template_id: str) -> ScriptTemplate:
    template = session.get(ScriptTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="脚本模板不存在")
    return template


@router.get("", response_model=list[ScriptTemplateRead])
def list_templates(session: Session = Depends(get_db_session)) -> list[ScriptTemplate]:
    return list(session.scalars(select(ScriptTemplate).order_by(ScriptTemplate.name)))


@router.post("", response_model=ScriptTemplateRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
def add_template(payload: ScriptTemplateCreate, session: Session = Depends(get_db_session)) -> ScriptTemplate:
    template = ScriptTemplate(**payload.model_dump())
    session.add(template)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="脚本模板名称已存在") from error
    session.refresh(template)
    return template


@router.patch("/{template_id}", response_model=ScriptTemplateRead, dependencies=[Depends(require_csrf)])
def edit_template(template_id: str, payload: ScriptTemplateUpdate, session: Session = Depends(get_db_session)) -> ScriptTemplate:
    template = require_template(session, template_id)
    changes = payload.model_dump(exclude_unset=True)
    if "body" in changes and changes["body"] != template.body:
        template.version += 1
    for field, value in changes.items():
        setattr(template, field, value)
    session.commit()
    session.refresh(template)
    return template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)])
def disable_template(template_id: str, session: Session = Depends(get_db_session)) -> Response:
    template = require_template(session, template_id)
    template.enabled = False
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
