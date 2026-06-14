from fastapi import APIRouter, Depends, HTTPException

from app.core.config import Settings, get_settings
from app.core.security import ApiClient, require_api_client
from app.providers.dify_knowledge import DifyKnowledgeProvider
from app.providers.neo4j_graph import Neo4jGraphProvider

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

