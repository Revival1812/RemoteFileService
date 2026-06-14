import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, jsonb_type


class PaperVersion(Base, TimestampMixin):
    __tablename__ = "paper_versions"
    __table_args__ = (
        UniqueConstraint("paper_id", "content_hash", name="uq_paper_versions_paper_hash"),
        UniqueConstraint("paper_id", "version_number", name="uq_paper_versions_paper_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    paper_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    profile_json: Mapped[dict[str, Any]] = mapped_column(jsonb_type, default=dict, nullable=False)
    chapter_index_json: Mapped[dict[str, Any] | None] = mapped_column(jsonb_type)
    figure_index_json: Mapped[dict[str, Any] | None] = mapped_column(jsonb_type)
    graph_json: Mapped[dict[str, Any] | None] = mapped_column(jsonb_type)
    source_metadata_json: Mapped[dict[str, Any]] = mapped_column(jsonb_type, default=dict, nullable=False)
    knowledge_documents_json: Mapped[list[dict[str, Any]]] = mapped_column(jsonb_type, default=list, nullable=False)

    paper = relationship("Paper", back_populates="versions")

