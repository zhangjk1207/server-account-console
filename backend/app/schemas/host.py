from datetime import datetime
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_data_root(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.rstrip("/")
    if not normalized.startswith("/") or normalized == "":
        raise ValueError("数据根目录必须是非根目录的绝对路径")
    parts = PurePosixPath(normalized).parts
    if any(part in {".", ".."} for part in value.split("/")):
        raise ValueError("数据根目录不能包含路径跳转")
    if normalized == "/home" or normalized.startswith("/home/"):
        raise ValueError("数据根目录不能与 /home 重叠")
    if not parts:
        raise ValueError("数据根目录必须是非根目录的绝对路径")
    return normalized


class HostCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    address: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    ssh_user: str = Field(default="root", min_length=1, max_length=64, pattern=r"^[a-z_][a-z0-9_-]{0,31}$")
    tags: list[str] = Field(default_factory=list, max_length=20)
    data_root: str | None = Field(default=None, min_length=2, max_length=255)

    _normalize_data_root = field_validator("data_root")(normalize_data_root)


class HostUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    address: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    ssh_user: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-z_][a-z0-9_-]{0,31}$")
    tags: list[str] | None = Field(default=None, max_length=20)
    data_root: str | None = Field(default=None, min_length=2, max_length=255)

    _normalize_data_root = field_validator("data_root")(normalize_data_root)


class HostRead(BaseModel):
    id: str
    name: str
    address: str
    port: int
    ssh_user: str
    tags: list[str]
    data_root: str | None
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
