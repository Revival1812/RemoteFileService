import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, jsonb_type, utcnow


class Paper(Base, TimestampMixin):
    __tablename__ = "papers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    paper_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    canonical_title: Mapped[str | None] = mapped_column(Text)
    normalized_title: Mapped[str | None] = mapped_column(Text, index=True)
    doi: Mapped[str | None] = mapped_column(Text, unique=True)
    arxiv_id: Mapped[str | None] = mapped_column(Text, unique=True)
    authors_json: Mapped[dict[str, Any] | None] = mapped_column(jsonb_type)
    year: Mapped[int | None] = mapped_column(Integer)
    latest_content_hash: Mapped[str | None] = mapped_column(Text)
    latest_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="active", nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    versions = relationship("PaperVersion", back_populates="paper")
    jobs = relationship("IngestionJob", back_populates="paper")

