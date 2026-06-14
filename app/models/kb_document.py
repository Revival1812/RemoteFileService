import uuid
from typing import Any

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, jsonb_type


class KbDocument(Base, TimestampMixin):
    __tablename__ = "kb_documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    paper_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_id: Mapped[str | None] = mapped_column(Text)
    remote_document_id: Mapped[str | None] = mapped_column(Text)
    batch_id: Mapped[str | None] = mapped_column(Text)
    indexing_status: Mapped[str] = mapped_column(Text, default="pending", nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(jsonb_type, default=dict, nullable=False)

