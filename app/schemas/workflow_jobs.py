from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

WorkflowJobStatus = Literal[
    "queued",
    "uploading",
    "starting",
    "running",
    "reconnecting",
    "succeeded",
    "failed",
    "cancel_requested",
    "cancelled",
]

AccessScope = Literal["private", "shared", "public"]


class WorkflowArxivJobCreate(BaseModel):
    source_type: Literal["arxiv"] = "arxiv"
    arxiv_id: str = Field(..., min_length=1, examples=["2602.11929"])
    analysis_id: str = ""
    action: str = "analyze_arxiv"
    user_query: str = "请完整解析这篇论文"
    user_level: str = "研究生或研究人员"
    force_accept: bool = False
    allow_ingestion: bool = False
    parser_mode: str = "auto"
    analysis_depth: str = "full"
    owner_id: str = Field(..., min_length=1)
    access_scope: AccessScope = "private"


class WorkflowJobAccepted(BaseModel):
    job_id: str
    status: WorkflowJobStatus
    status_url: str
    result_url: str


class WorkflowJobStatusRead(BaseModel):
    job_id: str
    status: WorkflowJobStatus
    source_type: str
    owner_id: str | None = None
    access_scope: str
    current_node_id: str | None = None
    current_node_title: str | None = None
    event_count: int
    dify_workflow_run_id: str | None = None
    dify_task_id: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: dict[str, str | None] | None = None

    model_config = ConfigDict(from_attributes=True)


class WorkflowJobResultResponse(BaseModel):
    job_id: str
    status: WorkflowJobStatus
    view: Literal["summary", "full"]
    result: dict[str, Any] | None = None
    error: dict[str, str | None] | None = None


class WorkflowJobListResponse(BaseModel):
    items: list[WorkflowJobStatusRead]
    page: int
    page_size: int


class WorkflowCancelResponse(BaseModel):
    job_id: str
    status: WorkflowJobStatus


class WorkflowGatewayAdminStatus(BaseModel):
    enabled: bool
    dify_api_base_url: str
    redis_configured: bool
    postgres_configured: bool
    queue_name: str
    queued: int
    running: int
    reconnecting: int
    recent_failed: int

