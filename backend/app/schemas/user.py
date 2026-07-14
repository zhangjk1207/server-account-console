from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


USERNAME_PATTERN = r"^[a-z_][a-z0-9_-]{0,31}$"


class ManagedUserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=32, pattern=USERNAME_PATTERN)
    display_name: str = Field(default="", max_length=120)
    primary_group: str | None = Field(default=None, max_length=64)
    groups: list[str] = Field(default_factory=list, max_length=20)
    shell: str = Field(default="/bin/bash", min_length=1, max_length=255)
    home: str | None = Field(default=None, max_length=255)
    sudo_rule: str | None = Field(default=None, max_length=4096)


class ManagedUserUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    primary_group: str | None = Field(default=None, max_length=64)
    groups: list[str] | None = Field(default=None, max_length=20)
    shell: str | None = Field(default=None, min_length=1, max_length=255)
    home: str | None = Field(default=None, max_length=255)
    sudo_rule: str | None = Field(default=None, max_length=4096)
    enabled: bool | None = None


class ManagedUserRead(BaseModel):
    id: str
    username: str
    display_name: str
    primary_group: str | None
    groups: list[str]
    shell: str
    home: str | None
    sudo_rule: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SshPublicKeyCreate(BaseModel):
    public_key: str = Field(min_length=20, max_length=8192)


class SshPublicKeyRead(BaseModel):
    id: str
    managed_user_id: str
    public_key: str
    fingerprint: str
    comment: str
    enabled: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HostUserStateRead(BaseModel):
    host_id: str
    host_name: str
    status: str
    synced_at: datetime | None
    desired_hash: str | None
