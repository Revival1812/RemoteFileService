import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class IngestionJob(Base, TimestampMixin):
    __tablename__ = "ingestion_jobs"

    job_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    paper_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    status: Mapped[str] = mapped_column(Text, default="received", nullable=False)
    dedup_status: Mapped[str] = mapped_column(Text, nullable=False)
    kb_status: Mapped[str] = mapped_column(Text, default="skipped", nullable=False)
    graph_status: Mapped[str] = mapped_column(Text, default="skipped", nullable=False)
    storage_status: Mapped[str] = mapped_column(Text, default="disabled", nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    request_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    paper = relationship("Paper", back_populates="jobs")

