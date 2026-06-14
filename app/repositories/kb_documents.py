import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kb_document import KbDocument


class KbDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def by_paper(self, paper_uuid: uuid.UUID) -> list[KbDocument]:
        result = await self.session.scalars(
            select(KbDocument).where(KbDocument.paper_id == paper_uuid).order_by(KbDocument.created_at.desc())
        )
        return list(result)

