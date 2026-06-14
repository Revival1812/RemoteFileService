import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import ApiClient, require_api_client
from app.db.session import get_session
from app.models.paper import Paper
from app.schemas.ingestion import RetryJobResponse
from app.schemas.knowledge import KbDocumentRead
from app.schemas.paper import (
    DuplicateCandidateRead,
    DuplicateCandidateUpdate,
    PaperListResponse,
    PaperRead,
    PaperVersionRead,
)
from app.services.paper_service import PaperService

router = APIRouter(prefix="/v1/papers", tags=["papers"])
duplicates_router = APIRouter(prefix="/v1/duplicates", tags=["duplicates"])


@router.get("", response_model=PaperListResponse, summary="List registered papers")
async def list_papers(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: ApiClient = Depends(require_api_client),
    session: AsyncSession = Depends(get_session),
) -> PaperListResponse:
    papers = await PaperService(session).list_papers(limit=limit, offset=offset)
    return PaperListResponse(items=[_paper_read(item) for item in papers], limit=limit, offset=offset)


@router.get("/{paper_id}", response_model=PaperRead, summary="Get a paper by external paper_id")
async def get_paper(
    paper_id: str,
    client: ApiClient = Depends(require_api_client),
    session: AsyncSession = Depends(get_session),
) -> PaperRead:
    paper = await PaperService(session).get_visible_paper(paper_id, client)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return _paper_read(paper)


@router.get("/{paper_id}/versions", response_model=list[PaperVersionRead], summary="List paper versions")
async def get_paper_versions(
    paper_id: str,
    client: ApiClient = Depends(require_api_client),
    session: AsyncSession = Depends(get_session),
) -> list[PaperVersionRead]:
    service = PaperService(session)
    paper = await service.get_visible_paper(paper_id, client)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    versions = await service.versions(paper)
    return [
        PaperVersionRead(
            id=str(version.id),
            paper_id=paper.paper_id,
            version_number=version.version_number,
            content_hash=version.content_hash,
            profile_json=version.profile_json,
            graph_json=version.graph_json,
            source_metadata_json=version.source_metadata_json,
            knowledge_documents_json=version.knowledge_documents_json,
            created_at=version.created_at,
        )
        for version in versions
    ]


@router.get("/{paper_id}/documents", response_model=list[KbDocumentRead], summary="List Dify knowledge documents for a paper")
async def get_paper_documents(
    paper_id: str,
    client: ApiClient = Depends(require_api_client),
    session: AsyncSession = Depends(get_session),
) -> list[KbDocumentRead]:
    service = PaperService(session)
    paper = await service.get_visible_paper(paper_id, client)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    docs = await service.documents(paper)
    return [
        KbDocumentRead(
            document_key=doc.document_key,
            content_hash=doc.content_hash,
            provider=doc.provider,
            dataset_id=doc.dataset_id,
            remote_document_id=doc.remote_document_id,
            batch_id=doc.batch_id,
            indexing_status=doc.indexing_status,
            metadata=doc.metadata_json,
        )
        for doc in docs
    ]


@router.post("/{paper_id}/sync", status_code=status.HTTP_202_ACCEPTED, response_model=RetryJobResponse, summary="Request paper resync")
async def sync_paper(
    paper_id: str,
    _: ApiClient = Depends(require_api_client),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> RetryJobResponse:
    raise HTTPException(status_code=501, detail="Manual paper resync is reserved for a later version; retry a job instead")


@duplicates_router.get("", response_model=list[DuplicateCandidateRead], summary="List possible duplicate papers")
async def list_duplicates(
    _: ApiClient = Depends(require_api_client),
    session: AsyncSession = Depends(get_session),
) -> list[DuplicateCandidateRead]:
    duplicates = await PaperService(session).duplicates()
    return [
        DuplicateCandidateRead(
            id=str(item.id),
            paper_id_a=item.paper_id_a,
            paper_id_b=item.paper_id_b,
            similarity_score=float(item.similarity_score),
            reason=item.reason,
            review_status=item.review_status,
            created_at=item.created_at,
        )
        for item in duplicates
    ]


@duplicates_router.patch("/{id}", response_model=DuplicateCandidateRead, summary="Update duplicate review status")
async def update_duplicate(
    id: uuid.UUID,
    payload: DuplicateCandidateUpdate,
    _: ApiClient = Depends(require_api_client),
    session: AsyncSession = Depends(get_session),
) -> DuplicateCandidateRead:
    item = await PaperService(session).update_duplicate(id, payload.review_status)
    if item is None:
        raise HTTPException(status_code=404, detail="Duplicate candidate not found")
    return DuplicateCandidateRead(
        id=str(item.id),
        paper_id_a=item.paper_id_a,
        paper_id_b=item.paper_id_b,
        similarity_score=float(item.similarity_score),
        reason=item.reason,
        review_status=item.review_status,
        created_at=item.created_at,
    )


def _paper_read(paper: Paper) -> PaperRead:
    return PaperRead(
        id=str(paper.id),
        paper_id=paper.paper_id,
        canonical_title=paper.canonical_title,
        normalized_title=paper.normalized_title,
        doi=paper.doi,
        arxiv_id=paper.arxiv_id,
        authors_json=paper.authors_json,
        year=paper.year,
        latest_content_hash=paper.latest_content_hash,
        latest_version=paper.latest_version,
        status=paper.status,
        created_at=paper.created_at,
        updated_at=paper.updated_at,
        last_seen_at=paper.last_seen_at,
    )

