import asyncio

from celery.utils.log import get_task_logger

from app.core.config import Settings, get_settings
from app.db.session import AsyncSessionLocal
from app.services.workflow_gateway_service import WorkflowJobRunner
from app.workers.celery_app import celery_app

task_logger = get_task_logger(__name__)


async def dispatch_workflow_job(job_id: str, settings: Settings) -> None:
    if settings.queue_mode == "celery":
        run_workflow_gateway_job.apply_async(args=[job_id], queue=settings.workflow_gateway_queue)
    return


async def run_workflow_gateway_job_async(job_id: str, settings: Settings | None = None) -> None:
    effective_settings = settings or get_settings()
    async with AsyncSessionLocal() as session:
        await WorkflowJobRunner(session, effective_settings).run(job_id)


async def recover_workflow_gateway_jobs_async(settings: Settings | None = None) -> int:
    effective_settings = settings or get_settings()
    async with AsyncSessionLocal() as session:
        return await WorkflowJobRunner(session, effective_settings).recover_unfinished()


@celery_app.task(
    bind=True,
    name="app.workers.workflow_tasks.run_workflow_gateway_job",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=get_settings().workflow_gateway_reconnect_max_attempts,
)
def run_workflow_gateway_job(self, job_id: str) -> None:
    task_logger.info("Starting workflow gateway job", extra={"extra_fields": {"job_id": job_id}})
    asyncio.run(run_workflow_gateway_job_async(job_id))


@celery_app.task(name="app.workers.workflow_tasks.recover_workflow_gateway_jobs")
def recover_workflow_gateway_jobs() -> int:
    task_logger.info("Recovering unfinished workflow gateway jobs")
    return asyncio.run(recover_workflow_gateway_jobs_async())
