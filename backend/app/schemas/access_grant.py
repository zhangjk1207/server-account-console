from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

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


class AccessGrantProvisionRow(BaseModel):
    host_id: str
    username: str = Field(min_length=1, max_length=32, pattern=USERNAME_PATTERN)
    permission_template_id: str | None = None
    groups_override: list[str] | None = Field(default=None, max_length=20)
    sudo_rule_override: str | None = Field(default=None, max_length=4096)


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
    data_directory: str
    state: str
    last_success_job_id: str | None
    updated_at: datetime


class AccessGrantRevokeRow(BaseModel):
    grant_id: str
    delete_data: bool = False


class AccessGrantRevokePreviewRequest(BaseModel):
    grants: list[AccessGrantRevokeRow] = Field(min_length=1, max_length=20)
