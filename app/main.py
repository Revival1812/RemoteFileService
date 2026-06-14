import logging
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status

from app.api import admin, health, ingestion, papers, retrieval
from app.core.config import get_settings
from app.core.logging import bind_request_context, configure_logging

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    docs_url = "/docs" if settings.enable_public_docs else None
    redoc_url = "/redoc" if settings.enable_public_docs else None
    openapi_url = "/openapi.json" if settings.enable_public_docs else None
    app = FastAPI(
        title="Paper Registry and Async Ingestion Service",
        version="0.1.0",
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        description="Registers structured paper outputs, deduplicates versions, and optionally syncs Dify Knowledge and Neo4j.",
    )

    @app.middleware("http")
    async def request_context_and_size_limit(
        request: Request,
        call_next: Callable[[Request], Awaitable[JSONResponse]],
    ):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        bind_request_context(request_id=request_id)
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.max_request_bytes:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={"detail": "Request body too large"},
                headers={"x-request-id": request_id},
            )
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content=jsonable_encoder({"detail": exc.errors()}))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled application error")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    app.include_router(health.router)
    app.include_router(ingestion.router)
    app.include_router(papers.router)
    app.include_router(papers.duplicates_router)
    app.include_router(admin.router)
    app.include_router(retrieval.router)
    return app


app = create_app()
