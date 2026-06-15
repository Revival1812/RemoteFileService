from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery(
    "paper_ingestion",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks", "app.workers.workflow_tasks"],
)
celery_app.conf.update(
    task_acks_late=True,
    task_default_retry_delay=1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_routes={
        "app.workers.workflow_tasks.*": {"queue": settings.workflow_gateway_queue},
    },
)
