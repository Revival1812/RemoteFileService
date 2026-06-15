import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, jsonb_type


class WorkflowJob(Base, TimestampMixin):
    __tablename__ = "workflow_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(Text, unique=True)
    source_type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued", index=True)
    owner_id: Mapped[str | None] = mapped_column(Text, index=True)
    access_scope: Mapped[str] = mapped_column(Text, nullable=False, default="private")
    dify_user: Mapped[str] = mapped_column(Text, nullable=False)
    dify_task_id: Mapped[str | None] = mapped_column(Text, index=True)
    dify_workflow_run_id: Mapped[str | None] = mapped_column(Text, index=True)
    dify_upload_file_id: Mapped[str | None] = mapped_column(Text)
    request_inputs_json: Mapped[dict[str, Any]] = mapped_column(jsonb_type, default=dict, nullable=False)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(jsonb_type)
    result_summary_json: Mapped[dict[str, Any] | None] = mapped_column(jsonb_type)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    current_node_id: Mapped[str | None] = mapped_column(Text)
    current_node_title: Mapped[str | None] = mapped_column(Text)
    event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    temporary_file_manifest_json: Mapped[list[dict[str, Any]]] = mapped_column(jsonb_type, default=list, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
