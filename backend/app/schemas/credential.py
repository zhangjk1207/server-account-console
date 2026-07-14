from datetime import datetime

from pydantic import BaseModel


class HostCredentialStatus(BaseModel):
    private_key_configured: bool
    sudo_password_configured: bool
    verified_at: datetime | None
    ssh_verified: bool | None
    sudo_verified: bool | None
    last_error: str | None


class HostCredentialProbe(BaseModel):
    fingerprint: str | None
    requires_confirmation: bool
    ssh_ok: bool | None
    sudo_ok: bool | None
    error: str | None
    latency_ms: int | None
