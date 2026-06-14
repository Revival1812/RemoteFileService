import uuid
from decimal import Decimal

from sqlalchemy import Numeric, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DuplicateCandidate(Base, TimestampMixin):
    __tablename__ = "duplicate_candidates"
    __table_args__ = (UniqueConstraint("paper_id_a", "paper_id_b", name="uq_duplicate_candidate_pair"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    paper_id_a: Mapped[str] = mapped_column(Text, nullable=False)
    paper_id_b: Mapped[str] = mapped_column(Text, nullable=False)
    similarity_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    review_status: Mapped[str] = mapped_column(Text, default="pending", nullable=False)

