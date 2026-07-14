from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.user import USERNAME_PATTERN


class HostAuthorizedKeyRead(BaseModel):
    public_key: str
    fingerprint: str
    comment: str


class HostUserRead(BaseModel):
    username: str
    uid: int
    primary_group: str
    groups: list[str]
    shell: str
    home: str
    locked: bool | None
    expires_at: date | None
    public_keys: list[HostAuthorizedKeyRead] = Field(default_factory=list)


class HostUserOperation(BaseModel):
    action: Literal["upsert", "lock", "unlock", "reset_password", "delete", "keys"]
    username: str = Field(pattern=USERNAME_PATTERN)
    remove_home: bool = False
    managed_user_id: str | None = None
    primary_group: str | None = None
    groups: list[str] | None = None
    shell: str | None = None
    home: str | None = None
    sudo_rule: str | None = None
    expires_at: date | None = None
    public_keys: list[str] | None = None
    key_mode: Literal["append", "remove", "replace"] | None = None

    @model_validator(mode="after")
    def validate_key_operation(self) -> "HostUserOperation":
        if self.action == "keys" and (not self.public_keys or self.key_mode is None):
            raise ValueError("公钥操作需要指定公钥和操作方式")
        if self.action != "keys" and self.key_mode is not None:
            raise ValueError("仅公钥操作可设置公钥操作方式")
        return self


class HostOperationExecute(BaseModel):
    new_password: str | None = Field(default=None, min_length=1, max_length=1024)


class SshPasswordAuthenticationRead(BaseModel):
    enabled: bool


class SshPasswordAuthenticationPreview(BaseModel):
    enabled: bool
