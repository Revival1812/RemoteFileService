import re
from decimal import Decimal
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.duplicate_candidate import DuplicateCandidate
from app.models.paper import Paper


def normalize_title(title: str | None) -> str | None:
    if not title:
        return None
    normalized = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    return re.sub(r"\s+", " ", normalized)


class DeduplicationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_possible_duplicate(self, *, paper_id: str, normalized_title: str | None) -> tuple[str, float] | None:
        if not normalized_title:
            return None
        result = await self.session.scalars(select(Paper).where(Paper.paper_id != paper_id, Paper.normalized_title.is_not(None)))
        best: tuple[str, float] | None = None
        for paper in result:
            score = SequenceMatcher(None, normalized_title, paper.normalized_title or "").ratio()
            if score >= 0.92 and (best is None or score > best[1]):
                best = (paper.paper_id, score)
        return best

    async def create_candidate(self, *, paper_id_a: str, paper_id_b: str, score: float, reason: str) -> None:
        a, b = sorted([paper_id_a, paper_id_b])
        if self.session.bind and self.session.bind.dialect.name == "postgresql":
            stmt = (
                pg_insert(DuplicateCandidate)
                .values(
                    paper_id_a=a,
                    paper_id_b=b,
                    similarity_score=Decimal(str(round(score, 4))),
                    reason=reason,
                    review_status="pending",
                )
                .on_conflict_do_nothing(index_elements=["paper_id_a", "paper_id_b"])
            )
            await self.session.execute(stmt)
            return
        existing = await self.session.scalar(
            select(DuplicateCandidate).where(
                DuplicateCandidate.paper_id_a == a,
                DuplicateCandidate.paper_id_b == b,
            )
        )
        if existing is None:
            self.session.add(
                DuplicateCandidate(
                    paper_id_a=a,
                    paper_id_b=b,
                    similarity_score=Decimal(str(round(score, 4))),
                    reason=reason,
                    review_status="pending",
                )
            )

