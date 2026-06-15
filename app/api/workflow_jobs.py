from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import ApiClient, require_api_client
from app.db.session import get_session
from app.schemas.workflow_jobs import (
    WorkflowArxivJobCreate,
    WorkflowCancelResponse,
    WorkflowJobAccepted,
    WorkflowJobListResponse,
    WorkflowJobResultResponse,
    WorkflowJobStatusRead,
)
from app.services.workflow_gateway_service import WorkflowGatewayService

router = APIRouter(prefix="/v1/workflow-jobs", tags=["workflow-gateway"])


@router.post(
    "/arxiv",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=WorkflowJobAccepted,
    summary="Submit a long-running Dify workflow job for an arXiv paper",
)
async def submit_arxiv_workflow_job(
    payload: WorkflowArxivJobCreate,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    client: ApiClient = Depends(require_api_client),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> WorkflowJobAccepted:
    return await WorkflowGatewayService(session, settings).create_arxiv_job(
        payload,
        client=client,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=WorkflowJobAccepted,
    summary="Submit a long-running Dify workflow job with uploaded paper files",
)
async def submit_upload_workflow_job(
    request: Request,
    paper_file: UploadFile = File(...),
    supplementary_images: list[UploadFile] | None = File(default=None),
    analysis_id: str = Form(default=""),
    action: str = Form(default="new_upload"),
    user_query: str = Form(default="请完整解析这篇论文"),
    user_level: str = Form(default="研究生或研究人员"),
    force_accept: bool = Form(default=False),
    allow_ingestion: bool = Form(default=False),
    parser_mode: str = Form(default="auto"),
    analysis_depth: str = Form(default="full"),
    owner_id: str = Form(...),
    access_scope: str = Form(default="private"),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    client: ApiClient = Depends(require_api_client),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> WorkflowJobAccepted:
    form_data = await request.form()
    if len(form_data.getlist("paper_file")) != 1:
        raise HTTPException(status_code=422, detail="paper_file must be a single file")
    return await WorkflowGatewayService(session, settings).create_upload_job(
        paper_file=paper_file,
        supplementary_images=supplementary_images or [],
        form={
            "analysis_id": analysis_id,
            "action": action,
            "user_query": user_query,
            "user_level": user_level,
            "force_accept": force_accept,
            "allow_ingestion": allow_ingestion,
            "parser_mode": parser_mode,
            "analysis_depth": analysis_depth,
            "owner_id": owner_id,
            "access_scope": access_scope,
        },
        client=client,
        idempotency_key=idempotency_key,
    )


@router.get("", response_model=WorkflowJobListResponse, summary="List Dify workflow gateway jobs")
async def list_workflow_jobs(
    owner_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    source_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    client: ApiClient = Depends(require_api_client),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> WorkflowJobListResponse:
    service = WorkflowGatewayService(session, settings)
    service.ensure_enabled()
    return await service.list_jobs(
        client=client,
        owner_id=owner_id,
        status_filter=status_filter,
        source_type=source_type,
        page=page,
        page_size=page_size,
    )


@router.get("/{job_id}", response_model=WorkflowJobStatusRead, summary="Get Dify workflow gateway job status")
async def get_workflow_job(
    job_id: str,
    client: ApiClient = Depends(require_api_client),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> WorkflowJobStatusRead:
    service = WorkflowGatewayService(session, settings)
    service.ensure_enabled()
    return await service.read_status(job_id, client)


@router.get("/{job_id}/result", response_model=WorkflowJobResultResponse, summary="Get Dify workflow gateway job result")
async def get_workflow_job_result(
    job_id: str,
    view: str = Query(default="summary", pattern="^(summary|full)$"),
    client: ApiClient = Depends(require_api_client),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> WorkflowJobResultResponse:
    service = WorkflowGatewayService(session, settings)
    service.ensure_enabled()
    return await service.read_result(job_id, view=view, client=client)


@router.post("/{job_id}/cancel", response_model=WorkflowCancelResponse, summary="Cancel a Dify workflow gateway job")
async def cancel_workflow_job(
    job_id: str,
    client: ApiClient = Depends(require_api_client),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> WorkflowCancelResponse:
    service = WorkflowGatewayService(session, settings)
    service.ensure_enabled()
    return await service.cancel_job(job_id, client=client)
