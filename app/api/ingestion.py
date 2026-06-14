import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import ApiClient, require_api_client
from app.db.session import get_session
from app.models.ingestion_job import IngestionJob
from app.repositories.jobs import JobRepository
from app.repositories.papers import PaperRepository
from app.schemas.ingestion import IngestionAcceptedResponse, IngestionJobCreate, RetryJobResponse
from app.schemas.job import JobRead
from app.services.ingestion_service import IngestionService
from app.services.job_service import JobService
from app.workers.tasks import dispatch_sync_job

router = APIRouter(prefix="/v1/ingestion/jobs", tags=["ingestion"])


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IngestionAcceptedResponse,
    summary="Register a paper ingestion job",
    description="Accepts Dify workflow output, performs transactional PostgreSQL registration and deduplication, then dispatches optional provider sync.",
)
async def create_ingestion_job(
    payload: IngestionJobCreate,
    _: ApiClient = Depends(require_api_client),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> IngestionAcceptedResponse:
    return await IngestionService(session, settings).submit(payload)


@router.get(
    "/{job_id}",
    response_model=JobRead,
    summary="Get ingestion job status",
    description="Returns deduplication and provider synchronization status for a job.",
)
async def get_ingestion_job(
    job_id: uuid.UUID,
    _: ApiClient = Depends(require_api_client),
    session: AsyncSession = Depends(get_session),
) -> JobRead:
    job = await JobRepository(session).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    paper = await PaperRepository(session).get_by_uuid(job.paper_id)
    return _job_read(job, paper.paper_id if paper else str(job.paper_id))


@router.post(
    "/{job_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RetryJobResponse,
    summary="Retry a failed or partial ingestion job",
)
async def retry_ingestion_job(
    job_id: uuid.UUID,
    _: ApiClient = Depends(require_api_client),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> RetryJobResponse:
    job = await JobRepository(session).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    await JobService(session, settings).retry(str(job_id))
    await dispatch_sync_job(str(job_id), settings)
    return RetryJobResponse(job_id=str(job_id))


def _job_read(job: IngestionJob, public_paper_id: str) -> JobRead:
    return JobRead(
        job_id=str(job.job_id),
        paper_id=public_paper_id,
        content_hash=job.content_hash,
        status=job.status,
        dedup_status=job.dedup_status,
        kb_status=job.kb_status,
        graph_status=job.graph_status,
        storage_status=job.storage_status,
        retry_count=job.retry_count,
        error_message=job.error_message,
        request_schema_version=job.request_schema_version,
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
    )

