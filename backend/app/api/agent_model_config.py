import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import require_admin, require_csrf
from app.db.models import AgentModelConfig
from app.db.session import get_db_session
from app.schemas.agent_model_config import AgentModelConfigInternal, AgentModelConfigRead, AgentModelConfigUpdate
from app.services.credentials import CredentialCipher, CredentialConfigurationError

router = APIRouter(prefix="/agent-model-config", tags=["agent-model-config"])


def current_config(session: Session) -> AgentModelConfig | None:
    return session.scalar(select(AgentModelConfig).order_by(AgentModelConfig.updated_at.desc()).limit(1))


def cipher_or_503() -> CredentialCipher:
    try:
        return CredentialCipher.from_settings()
    except CredentialConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error


def public_config(config: AgentModelConfig) -> AgentModelConfigRead:
    return AgentModelConfigRead(
        provider=config.provider,
        model=config.model,
        base_url=config.base_url,
        thinking_level=config.thinking_level,
        enabled=config.enabled,
        api_key_configured=bool(config.api_key_ciphertext),
    )


@router.get("", response_model=AgentModelConfigRead | None, dependencies=[Depends(require_admin)])
def get_config(session: Session = Depends(get_db_session)) -> AgentModelConfigRead | None:
    config = current_config(session)
    return None if config is None else public_config(config)


@router.put("", response_model=AgentModelConfigRead, dependencies=[Depends(require_admin), Depends(require_csrf)])
def put_config(payload: AgentModelConfigUpdate, session: Session = Depends(get_db_session)) -> AgentModelConfigRead:
    config = current_config(session)
    if config is None:
        if not payload.api_key:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="首次配置必须填写 API Key")
        config = AgentModelConfig(provider=payload.provider, model=payload.model, api_key_ciphertext="")
        session.add(config)
    if payload.api_key:
        config.api_key_ciphertext = cipher_or_503().encrypt(payload.api_key)
    config.provider = payload.provider
    config.model = payload.model
    config.base_url = None if payload.base_url is None else str(payload.base_url).rstrip("/")
    config.thinking_level = payload.thinking_level
    config.enabled = payload.enabled
    session.commit()
    session.refresh(config)
    return public_config(config)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin), Depends(require_csrf)])
def delete_config(session: Session = Depends(get_db_session)) -> Response:
    config = current_config(session)
    if config is not None:
        session.delete(config)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/internal", response_model=AgentModelConfigInternal)
def get_internal_config(
    x_agent_runtime_token: str | None = Header(default=None),
    session: Session = Depends(get_db_session),
) -> AgentModelConfigInternal:
    expected = get_settings().agent_runtime_token
    if not expected or not x_agent_runtime_token or not secrets.compare_digest(expected, x_agent_runtime_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Agent Runtime 未授权")
    config = current_config(session)
    if config is None or not config.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="尚未启用 Agent 模型")
    return AgentModelConfigInternal(
        provider=config.provider,
        model=config.model,
        base_url=config.base_url,
        api_key=cipher_or_503().decrypt(config.api_key_ciphertext),
        thinking_level=config.thinking_level,
        enabled=config.enabled,
    )
