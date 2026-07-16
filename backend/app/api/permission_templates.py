from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import require_admin, require_csrf
from app.db.models import PermissionTemplate
from app.db.session import get_db_session
from app.schemas.access_grant import PermissionTemplateCreate, PermissionTemplateRead, PermissionTemplateUpdate
from app.services.users import normalize_groups

router = APIRouter(prefix="/permission-templates", tags=["permission templates"], dependencies=[Depends(require_admin)])


def require_template(session: Session, template_id: str) -> PermissionTemplate:
    template = session.get(PermissionTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="权限模板不存在")
    return template


@router.get("", response_model=list[PermissionTemplateRead])
def list_templates(session: Session = Depends(get_db_session)) -> list[PermissionTemplate]:
    return list(session.scalars(select(PermissionTemplate).order_by(PermissionTemplate.name)))


@router.post("", response_model=PermissionTemplateRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
def add_template(payload: PermissionTemplateCreate, session: Session = Depends(get_db_session)) -> PermissionTemplate:
    template = PermissionTemplate(**payload.model_dump(exclude={"groups"}), groups=normalize_groups(payload.groups))
    session.add(template)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="权限模板名称已存在") from error
    session.refresh(template)
    return template


@router.patch("/{template_id}", response_model=PermissionTemplateRead, dependencies=[Depends(require_csrf)])
def edit_template(template_id: str, payload: PermissionTemplateUpdate, session: Session = Depends(get_db_session)) -> PermissionTemplate:
    template = require_template(session, template_id)
    changes = payload.model_dump(exclude_unset=True)
    if "groups" in changes and changes["groups"] is not None:
        changes["groups"] = normalize_groups(changes["groups"])
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
