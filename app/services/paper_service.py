import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ApiClient
from app.models.duplicate_candidate import DuplicateCandidate
from app.models.kb_document import KbDocument
from app.models.paper import Paper
from app.models.paper_version import PaperVersion
from app.repositories.kb_documents import KbDocumentRepository
from app.repositories.papers import PaperRepository


class PaperService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_visible_paper(self, paper_id: str, client: ApiClient | None) -> Paper | None:
        paper = await PaperRepository(self.session).get_by_public_id(paper_id)
        if paper is None:
            return None
        if client and client.is_admin:
            return paper
        latest = await PaperRepository(self.session).latest_version(paper.id)
        metadata = latest.source_metadata_json if latest else {}
        access_scope = metadata.get("access_scope", "private")
        owner_id = metadata.get("owner_id")
        if access_scope == "public":
            return paper
        if access_scope == "shared":
            return paper if client is not None else None
        if client is not None and client.owner_id is not None and client.owner_id == owner_id:
            return paper
        return None

    async def list_papers(self, *, limit: int, offset: int) -> list[Paper]:
        return await PaperRepository(self.session).list(limit=limit, offset=offset)

    async def versions(self, paper: Paper) -> list[PaperVersion]:
        return await PaperRepository(self.session).versions(paper.id)

    async def documents(self, paper: Paper) -> list[KbDocument]:
        return await KbDocumentRepository(self.session).by_paper(paper.id)

    async def duplicates(self) -> list[DuplicateCandidate]:
        result = await self.session.scalars(select(DuplicateCandidate).order_by(DuplicateCandidate.created_at.desc()))
        return list(result)

    async def update_duplicate(self, duplicate_id: uuid.UUID, review_status: str) -> DuplicateCandidate | None:
        duplicate = await self.session.get(DuplicateCandidate, duplicate_id)
        if duplicate is None:
            return None
        duplicate.review_status = review_status
        await self.session.commit()
        return duplicate
