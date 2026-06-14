from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JobRead(BaseModel):
    job_id: str
    paper_id: str
    content_hash: str
    status: str
    dedup_status: str
    kb_status: str
    graph_status: str
    storage_status: str
    retry_count: int
    error_message: str | None = None
    request_schema_version: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

