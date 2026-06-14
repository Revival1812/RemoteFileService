from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paper import Paper
from app.models.paper_version import PaperVersion


class PaperRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_public_id(self, paper_id: str, *, for_update: bool = False) -> Paper | None:
        stmt = select(Paper).where(Paper.paper_id == paper_id)
        if for_update:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def get_by_uuid(self, paper_uuid: uuid.UUID) -> Paper | None:
        return await self.session.get(Paper, paper_uuid)

    async def list(self, *, limit: int, offset: int) -> list[Paper]:
        result = await self.session.scalars(select(Paper).order_by(Paper.created_at.desc()).limit(limit).offset(offset))
        return list(result)

    async def versions(self, paper_uuid: uuid.UUID) -> list[PaperVersion]:
        result = await self.session.scalars(
            select(PaperVersion).where(PaperVersion.paper_id == paper_uuid).order_by(PaperVersion.version_number.desc())
        )
        return list(result)

    async def latest_version(self, paper_uuid: uuid.UUID) -> PaperVersion | None:
        return await self.session.scalar(
            select(PaperVersion)
            .where(PaperVersion.paper_id == paper_uuid)
            .order_by(PaperVersion.version_number.desc())
            .limit(1)
        )
