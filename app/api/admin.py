from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import ApiClient, require_api_client
from app.db.session import get_session
from app.models.workflow_job import WorkflowJob
from app.providers.dify_knowledge import DifyKnowledgeProvider
from app.providers.neo4j_graph import Neo4jGraphProvider
from app.schemas.workflow_jobs import WorkflowGatewayAdminStatus

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.post("/bootstrap", response_model=dict[str, object], summary="Bootstrap enabled providers")
async def bootstrap_providers(
    client: ApiClient = Depends(require_api_client),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    if not client.is_admin:
        raise HTTPException(status_code=403, detail="Admin key required")
    results: dict[str, object] = {}
    if settings.enable_dify_sync and settings.dify_kb_api_key:
        provider = DifyKnowledgeProvider(settings)
        try:
            results["dify_metadata_fields"] = await provider.ensure_metadata_fields()
        finally:
            await provider.close()
    if settings.enable_neo4j_sync and settings.neo4j_password:
        provider = Neo4jGraphProvider(settings)
        try:
            await provider.initialize()
            results["neo4j"] = "initialized"
        finally:
            await provider.close()
    return {"ok": True, "results": results}


@router.get("/providers/status", response_model=dict[str, object], summary="Get provider configuration status")
async def provider_status(_: ApiClient = Depends(require_api_client), settings: Settings = Depends(get_settings)) -> dict[str, object]:
    return {
        "dify": {"enabled": settings.enable_dify_sync, "configured": bool(settings.dify_kb_api_key and settings.dify_papers_dataset_id)},
        "neo4j": {"enabled": settings.enable_neo4j_sync, "configured": bool(settings.neo4j_password)},
        "object_storage": {"enabled": settings.enable_object_storage, "configured": bool(settings.s3_bucket)},
    }


@router.get(
    "/workflow-gateway/status",
    response_model=WorkflowGatewayAdminStatus,
    summary="Get Dify workflow gateway operational status",
)
async def workflow_gateway_status(
    client: ApiClient = Depends(require_api_client),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> WorkflowGatewayAdminStatus:
    if not client.is_admin:
        raise HTTPException(status_code=403, detail="Admin key required")
    postgres_configured = False
    redis_configured = False
    try:
        await session.execute(text("SELECT 1"))
        postgres_configured = True
    except Exception:
        postgres_configured = False
    redis_client = Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
    try:
        redis_configured = bool(await redis_client.ping())
    except Exception:
        redis_configured = False
    finally:
        await redis_client.aclose()
    queued = await _count_status(session, "queued")
    running = await _count_status(session, "running")
    reconnecting = await _count_status(session, "reconnecting")
    recent_failed = await _count_status(session, "failed")
    return WorkflowGatewayAdminStatus(
        enabled=settings.enable_workflow_gateway,
        dify_api_base_url=settings.dify_workflow_api_base_url,
        redis_configured=redis_configured,
        postgres_configured=postgres_configured,
        queue_name=settings.workflow_gateway_queue,
        queued=queued,
        running=running,
        reconnecting=reconnecting,
        recent_failed=recent_failed,
    )


async def _count_status(session: AsyncSession, status: str) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(WorkflowJob).where(WorkflowJob.status == status)) or 0
    )
