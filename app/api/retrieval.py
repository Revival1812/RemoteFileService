from fastapi import APIRouter, Depends, HTTPException

from app.core.config import Settings, get_settings
from app.core.security import ApiClient, require_api_client
from app.schemas.knowledge import ExternalRetrievalRequest, ExternalRetrievalResponse

router = APIRouter(prefix="/v1/retrieval", tags=["retrieval"])


@router.post("", response_model=ExternalRetrievalResponse, summary="Reserved external knowledge retrieval endpoint")
async def retrieve(
    payload: ExternalRetrievalRequest,
    _: ApiClient = Depends(require_api_client),
    settings: Settings = Depends(get_settings),
) -> ExternalRetrievalResponse:
    if not settings.enable_external_retrieval_api:
        raise HTTPException(status_code=404, detail="External retrieval API disabled")
    raise HTTPException(status_code=501, detail="External retrieval is not implemented yet")

