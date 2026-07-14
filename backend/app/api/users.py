from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import require_admin, require_csrf
from app.db.models import Host, HostUserState, ManagedUser, SshPublicKey
from app.db.session import get_db_session
from app.schemas.user import (
    HostUserStateRead,
    ManagedUserCreate,
    ManagedUserRead,
    ManagedUserUpdate,
    SshPublicKeyCreate,
    SshPublicKeyRead,
)
from app.services.users import normalize_groups, parse_public_key

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_admin)])


def require_user(session: Session, user_id: str) -> ManagedUser:
    user = session.get(ManagedUser, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return user


@router.get("", response_model=list[ManagedUserRead])
def list_users(session: Session = Depends(get_db_session)) -> list[ManagedUser]:
    return list(session.scalars(select(ManagedUser).order_by(ManagedUser.username)))


@router.post("", response_model=ManagedUserRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
def add_user(payload: ManagedUserCreate, session: Session = Depends(get_db_session)) -> ManagedUser:
    values = payload.model_dump()
    values["groups"] = normalize_groups(payload.groups)
    user = ManagedUser(**values)
    if user.home is None:
        user.home = f"/home/{user.username}"
    session.add(user)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Linux 用户名已存在") from error
    session.refresh(user)
    return user


@router.get("/{user_id}", response_model=ManagedUserRead)
def get_user(user_id: str, session: Session = Depends(get_db_session)) -> ManagedUser:
    return require_user(session, user_id)


@router.patch("/{user_id}", response_model=ManagedUserRead, dependencies=[Depends(require_csrf)])
def edit_user(user_id: str, payload: ManagedUserUpdate, session: Session = Depends(get_db_session)) -> ManagedUser:
    user = require_user(session, user_id)
    changes = payload.model_dump(exclude_unset=True)
    if "groups" in changes and changes["groups"] is not None:
        changes["groups"] = normalize_groups(changes["groups"])
    for field, value in changes.items():
        setattr(user, field, value)
    session.commit()
    session.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)])
def disable_user(user_id: str, session: Session = Depends(get_db_session)) -> Response:
    user = require_user(session, user_id)
    user.enabled = False
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{user_id}/keys", response_model=list[SshPublicKeyRead])
def list_keys(user_id: str, session: Session = Depends(get_db_session)) -> list[SshPublicKey]:
    require_user(session, user_id)
    return list(session.scalars(select(SshPublicKey).where(SshPublicKey.managed_user_id == user_id).order_by(SshPublicKey.created_at)))


@router.post("/{user_id}/keys", response_model=SshPublicKeyRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
def add_key(user_id: str, payload: SshPublicKeyCreate, session: Session = Depends(get_db_session)) -> SshPublicKey:
    require_user(session, user_id)
    try:
        public_key, fingerprint, comment = parse_public_key(payload.public_key)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    key = SshPublicKey(managed_user_id=user_id, public_key=public_key, fingerprint=fingerprint, comment=comment)
    session.add(key)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SSH 公钥已存在") from error
    session.refresh(key)
    return key


@router.delete("/{user_id}/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)])
def disable_key(user_id: str, key_id: str, session: Session = Depends(get_db_session)) -> Response:
    require_user(session, user_id)
    key = session.scalar(select(SshPublicKey).where(SshPublicKey.id == key_id, SshPublicKey.managed_user_id == user_id))
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSH 公钥不存在")
    key.enabled = False
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{user_id}/host-states", response_model=list[HostUserStateRead])
def list_host_states(user_id: str, session: Session = Depends(get_db_session)) -> list[HostUserStateRead]:
    require_user(session, user_id)
    rows = session.execute(
        select(HostUserState, Host).join(Host, Host.id == HostUserState.host_id).where(HostUserState.managed_user_id == user_id)
    )
    return [
        HostUserStateRead(
            host_id=state.host_id,
            host_name=host.name,
            status="synced" if state.last_success_job_id else "pending",
            synced_at=state.synced_at,
            desired_hash=state.desired_hash,
        )
        for state, host in rows
    ]
