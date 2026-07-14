from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class HostCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    address: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    ssh_user: str = Field(default="root", min_length=1, max_length=64, pattern=r"^[a-z_][a-z0-9_-]{0,31}$")
    tags: list[str] = Field(default_factory=list, max_length=20)


class HostUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    address: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    ssh_user: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-z_][a-z0-9_-]{0,31}$")
    tags: list[str] | None = Field(default=None, max_length=20)


class HostRead(BaseModel):
    id: str
    name: str
    address: str
    port: int
    ssh_user: str
    tags: list[str]
    host_key_fingerprint: str | None
    status: str
    archived: bool
    last_probe_at: datetime | None
    last_probe_latency_ms: int | None
    last_probe_error: str | None

    model_config = ConfigDict(from_attributes=True)


class FingerprintConfirmation(BaseModel):
    fingerprint: str = Field(min_length=10, max_length=128)


class HostProbeRead(BaseModel):
    status: str
    fingerprint: str | None
    reachable: bool
    latency_ms: int | None
    error: str | None
    requires_confirmation: bool
