from datetime import datetime

from pydantic import BaseModel, Field


class PreviewRequest(BaseModel):
    user_id: str
    host_ids: list[str] = Field(min_length=1, max_length=20)
    script_template_id: str | None = None


class JobTargetRead(BaseModel):
    host_id: str
    host_name: str
    state: str
    output: str
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None


class JobRead(BaseModel):
    id: str
    kind: str
    state: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    user_snapshot: dict
    request_snapshot: dict
    script_snapshot: dict | None
    targets: list[JobTargetRead]


class JobEventRead(BaseModel):
    id: str
    job_id: str
    host_id: str | None
    level: str
    message: str
    created_at: datetime
