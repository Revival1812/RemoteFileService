import asyncio
import logging

from celery.utils.log import get_task_logger

from app.core.config import Settings, get_settings
from app.db.session import AsyncSessionLocal
from app.services.job_service import JobService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
task_logger = get_task_logger(__name__)


async def run_sync_job(job_id: str, settings: Settings | None = None) -> None:
    effective_settings = settings or get_settings()
    async with AsyncSessionLocal() as session:
        await JobService(session, effective_settings).sync_job(job_id)


async def dispatch_sync_job(job_id: str, settings: Settings) -> None:
    if settings.queue_mode == "celery":
        sync_ingestion_job.delay(job_id)
        return
    await run_sync_job(job_id, settings)


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=get_settings().max_retry_count,
)
def sync_ingestion_job(self, job_id: str) -> None:
    task_logger.info("Starting ingestion sync job", extra={"extra_fields": {"job_id": job_id}})
    asyncio.run(run_sync_job(job_id))

