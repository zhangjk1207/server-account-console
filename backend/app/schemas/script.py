from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ScriptTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    description: str = Field(default="", max_length=2000)
    body: str = Field(min_length=1, max_length=65536)


class ScriptTemplateUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=2000)
    body: str | None = Field(default=None, min_length=1, max_length=65536)
    enabled: bool | None = None


class ScriptTemplateRead(BaseModel):
    id: str
    name: str
    description: str
    body: str
    version: int
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
