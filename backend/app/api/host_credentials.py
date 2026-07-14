from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.security import require_admin, require_csrf
from app.db.models import Host, HostCredential
from app.db.session import get_db_session
from app.schemas.credential import HostCredentialStatus
from app.services.credentials import CredentialCipher, CredentialConfigurationError, validate_private_key


router = APIRouter(prefix="/hosts", tags=["host-credentials"], dependencies=[Depends(require_admin)])


def require_host(session: Session, host_id: str) -> Host:
    host = session.get(Host, host_id)
    if host is None or host.archived:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="机器不存在")
    return host


def credential_status(credential: HostCredential | None) -> HostCredentialStatus:
    return HostCredentialStatus(
        private_key_configured=credential is not None,
        sudo_password_configured=credential is not None,
        verified_at=None if credential is None else credential.verified_at,
        ssh_verified=None if credential is None else credential.ssh_verified,
        sudo_verified=None if credential is None else credential.sudo_verified,
        last_error=None if credential is None else credential.last_error,
    )


def require_cipher() -> CredentialCipher:
    try:
        return CredentialCipher.from_settings()
    except CredentialConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error


@router.get("/{host_id}/credentials", response_model=HostCredentialStatus)
def get_credentials(host_id: str, session: Session = Depends(get_db_session)) -> HostCredentialStatus:
    require_host(session, host_id)
    return credential_status(session.query(HostCredential).filter(HostCredential.host_id == host_id).one_or_none())


@router.put("/{host_id}/credentials", response_model=HostCredentialStatus, dependencies=[Depends(require_csrf)])
async def put_credentials(
    host_id: str,
    private_key_file: UploadFile = File(...),
    sudo_password: str = Form(..., min_length=1, max_length=1024),
    session: Session = Depends(get_db_session),
) -> HostCredentialStatus:
    require_host(session, host_id)
    cipher = require_cipher()
    try:
        private_key = validate_private_key(await private_key_file.read())
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    credential = session.query(HostCredential).filter(HostCredential.host_id == host_id).one_or_none()
    if credential is None:
        credential = HostCredential(host_id=host_id, private_key_ciphertext="", sudo_password_ciphertext="")
        session.add(credential)
    credential.private_key_ciphertext = cipher.encrypt(private_key)
    credential.sudo_password_ciphertext = cipher.encrypt(sudo_password)
    credential.verified_at = None
    credential.ssh_verified = None
    credential.sudo_verified = None
    credential.last_error = None
    session.commit()
    return credential_status(credential)


@router.delete("/{host_id}/credentials", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)])
def delete_credentials(host_id: str, session: Session = Depends(get_db_session)) -> None:
    require_host(session, host_id)
    credential = session.query(HostCredential).filter(HostCredential.host_id == host_id).one_or_none()
    if credential is not None:
        session.delete(credential)
        session.commit()
