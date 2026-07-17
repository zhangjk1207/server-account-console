from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.user import USERNAME_PATTERN


class PermissionTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._-]*$")
    description: str = Field(default="", max_length=2000)
    groups: list[str] = Field(default_factory=list, max_length=20)
    sudo_rule: str | None = Field(default=None, max_length=4096)


class PermissionTemplateUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=2000)
    groups: list[str] | None = Field(default=None, max_length=20)
    sudo_rule: str | None = Field(default=None, max_length=4096)
    enabled: bool | None = None


class PermissionTemplateRead(BaseModel):
    id: str
    name: str
    description: str
    groups: list[str]
    sudo_rule: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExistingAccountSnapshot(BaseModel):
    uid: int = Field(ge=1000, le=2_147_483_647)
    primary_group: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    home: str = Field(min_length=1, max_length=255, pattern=r"^/")


class AccessGrantProvisionRow(BaseModel):
    host_id: str
    username: str = Field(min_length=1, max_length=32, pattern=USERNAME_PATTERN)
    account_origin: Literal["created", "adopted"] = "created"
    existing_account: ExistingAccountSnapshot | None = None
    permission_template_id: str | None = None
    groups_override: list[str] | None = Field(default=None, max_length=20)
    sudo_rule_override: str | None = Field(default=None, max_length=4096)

    @model_validator(mode="after")
    def validate_account_origin(self) -> "AccessGrantProvisionRow":
        if self.account_origin == "adopted" and self.existing_account is None:
            raise ValueError("existing_account is required when adopting an existing account")
        if self.account_origin == "created" and self.existing_account is not None:
            raise ValueError("existing_account is only valid for adopted accounts")
        if self.account_origin == "adopted" and any(
            value is not None for value in (self.permission_template_id, self.groups_override, self.sudo_rule_override)
        ):
            raise ValueError("adopted accounts keep their existing groups and sudo policy")
        return self


class AccessGrantPreviewRequest(BaseModel):
    grants: list[AccessGrantProvisionRow] = Field(min_length=1, max_length=20)


class AccessGrantRead(BaseModel):
    id: str
    host_id: str
    host_name: str
    username: str
    permission_template_id: str | None
    template_name: str | None
    groups: list[str]
    sudo_rule: str | None
    account_origin: Literal["created", "adopted"]
    remote_uid: int | None
    remote_primary_group: str | None
    remote_home: str | None
    managed_key_fingerprints: list[str]
    data_directory: str | None
    state: str
    last_success_job_id: str | None
    updated_at: datetime


class AccessGrantRevokeRow(BaseModel):
    grant_id: str
    delete_data: bool = False


class AccessGrantRevokePreviewRequest(BaseModel):
    grants: list[AccessGrantRevokeRow] = Field(min_length=1, max_length=20)
