from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class PreviewRequest(BaseModel):
    user_id: str
    host_ids: list[str] = Field(min_length=1, max_length=20)
    script_template_id: str | None = None

class JobRead(BaseModel):
    id: str; kind: str; state: str; created_at: datetime; started_at: datetime | None; finished_at: datetime | None
    request_snapshot: dict
    model_config = ConfigDict(from_attributes=True)

class JobEventRead(BaseModel):
    id: str; job_id: str; host_id: str | None; level: str; message: str; created_at: datetime
    model_config = ConfigDict(from_attributes=True)
