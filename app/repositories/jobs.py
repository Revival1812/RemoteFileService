import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingestion_job import IngestionJob


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, job_id: uuid.UUID) -> IngestionJob | None:
        return await self.session.get(IngestionJob, job_id)

    async def by_paper_hash(self, paper_uuid: uuid.UUID, content_hash: str) -> IngestionJob | None:
        return await self.session.scalar(
            select(IngestionJob)
            .where(IngestionJob.paper_id == paper_uuid, IngestionJob.content_hash == content_hash)
            .order_by(IngestionJob.created_at.desc())
            .limit(1)
        )

