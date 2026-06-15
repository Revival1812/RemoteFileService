import asyncio
import mimetypes
import random
import secrets
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import ApiClient
from app.models.base import utcnow
from app.models.workflow_job import WorkflowJob
from app.providers.dify_workflow import DifyWorkflowProvider
from app.schemas.workflow_jobs import (
    WorkflowArxivJobCreate,
    WorkflowCancelResponse,
    WorkflowJobAccepted,
    WorkflowJobListResponse,
    WorkflowJobResultResponse,
    WorkflowJobStatusRead,
)

ACTIVE_STATUSES = {"queued", "uploading", "starting", "running", "reconnecting", "cancel_requested"}
FINAL_STATUSES = {"succeeded", "failed", "cancelled"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
DOCUMENT_MIME_PREFIXES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "application/octet-stream",
}
IMAGE_MIME_PREFIXES = {"image/png", "image/jpeg", "image/webp"}


class WorkflowGatewayService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def ensure_enabled(self) -> None:
        if not self.settings.enable_workflow_gateway:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow gateway disabled")

    async def create_arxiv_job(
        self,
        payload: WorkflowArxivJobCreate,
        *,
        client: ApiClient,
        idempotency_key: str | None,
    ) -> WorkflowJobAccepted:
        self.ensure_enabled()
        existing = await self._get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return self._accepted(existing)
        await self._enforce_owner_concurrency(payload.owner_id)
        inputs = payload.model_dump(mode="json")
        inputs["paper_file"] = None
        inputs["supplementary_images"] = []
        job = self._build_job(
            source_type="arxiv",
            owner_id=payload.owner_id,
            access_scope=payload.access_scope,
            inputs=inputs,
            idempotency_key=idempotency_key,
            manifest=[],
        )
        self.session.add(job)
        await self.session.commit()
        from app.workers.workflow_tasks import dispatch_workflow_job

        await dispatch_workflow_job(job.job_id, self.settings)
        return self._accepted(job)

    async def create_upload_job(
        self,
        *,
        paper_file: UploadFile,
        supplementary_images: list[UploadFile],
        form: dict[str, Any],
        client: ApiClient,
        idempotency_key: str | None,
    ) -> WorkflowJobAccepted:
        self.ensure_enabled()
        existing = await self._get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return self._accepted(existing)
        owner_id = str(form.get("owner_id") or client.owner_id or "")
        if not owner_id:
            raise HTTPException(status_code=422, detail="owner_id is required")
        access_scope = str(form.get("access_scope") or "private")
        if access_scope not in {"private", "shared", "public"}:
            raise HTTPException(status_code=422, detail="access_scope must be private, shared, or public")
        await self._enforce_owner_concurrency(owner_id)
        manifest = await self._store_uploads(paper_file=paper_file, supplementary_images=supplementary_images)
        inputs = {
            "source_type": "upload",
            "paper_file": None,
            "supplementary_images": [],
            "arxiv_id": "",
            "analysis_id": str(form.get("analysis_id") or ""),
            "action": str(form.get("action") or "new_upload"),
            "user_query": str(form.get("user_query") or "请完整解析这篇论文"),
            "user_level": str(form.get("user_level") or "研究生或研究人员"),
            "force_accept": _to_bool(form.get("force_accept")),
            "allow_ingestion": _to_bool(form.get("allow_ingestion")),
            "parser_mode": str(form.get("parser_mode") or "auto"),
            "analysis_depth": str(form.get("analysis_depth") or "full"),
            "owner_id": owner_id,
            "access_scope": access_scope,
        }
        job = self._build_job(
            source_type="upload",
            owner_id=owner_id,
            access_scope=access_scope,
            inputs=inputs,
            idempotency_key=idempotency_key,
            manifest=manifest,
        )
        self.session.add(job)
        await self.session.commit()
        from app.workers.workflow_tasks import dispatch_workflow_job

        await dispatch_workflow_job(job.job_id, self.settings)
        return self._accepted(job)

    async def get_job_for_client(self, job_id: str, client: ApiClient) -> WorkflowJob:
        job = await self._get_by_job_id(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Workflow job not found")
        if not self._can_access(job, client):
            raise HTTPException(status_code=403, detail="Workflow job not accessible")
        return job

    async def read_status(self, job_id: str, client: ApiClient) -> WorkflowJobStatusRead:
        return self.to_status_read(await self.get_job_for_client(job_id, client))

    async def read_result(self, job_id: str, *, view: str, client: ApiClient) -> WorkflowJobResultResponse:
        if view not in {"summary", "full"}:
            raise HTTPException(status_code=422, detail="view must be summary or full")
        job = await self.get_job_for_client(job_id, client)
        if job.status in {"queued", "uploading", "starting", "running", "reconnecting", "cancel_requested"}:
            raise HTTPException(status_code=202, detail="Workflow job is not finished")
        if job.status in {"failed", "cancelled"}:
            raise HTTPException(
                status_code=409,
                detail={"status": job.status, "error_code": job.error_code, "error_message": job.error_message},
            )
        result = job.result_summary_json if view == "summary" else job.result_json
        return WorkflowJobResultResponse(job_id=job.job_id, status=job.status, view=view, result=result)

    async def list_jobs(
        self,
        *,
        client: ApiClient,
        owner_id: str | None,
        status_filter: str | None,
        source_type: str | None,
        page: int,
        page_size: int,
    ) -> WorkflowJobListResponse:
        stmt = select(WorkflowJob).order_by(WorkflowJob.created_at.desc())
        if status_filter:
            stmt = stmt.where(WorkflowJob.status == status_filter)
        if source_type:
            stmt = stmt.where(WorkflowJob.source_type == source_type)
        if client.is_admin:
            if owner_id:
                stmt = stmt.where(WorkflowJob.owner_id == owner_id)
        else:
            if not client.owner_id:
                stmt = stmt.where(WorkflowJob.access_scope == "public")
            else:
                stmt = stmt.where((WorkflowJob.access_scope == "public") | (WorkflowJob.owner_id == client.owner_id))
                if owner_id and owner_id != client.owner_id:
                    raise HTTPException(status_code=403, detail="owner_id not accessible")
        result = await self.session.scalars(stmt.offset((page - 1) * page_size).limit(page_size))
        return WorkflowJobListResponse(
            items=[self.to_status_read(job) for job in result],
            page=page,
            page_size=page_size,
        )

    async def cancel_job(self, job_id: str, *, client: ApiClient) -> WorkflowCancelResponse:
        job = await self.get_job_for_client(job_id, client)
        if job.status in FINAL_STATUSES:
            return WorkflowCancelResponse(job_id=job.job_id, status=job.status)
        if job.dify_task_id:
            job.status = "cancel_requested"
            await self.session.commit()
            provider = DifyWorkflowProvider(self.settings)
            try:
                await provider.stop_task(task_id=job.dify_task_id, user=job.dify_user)
            finally:
                await provider.close()
        job.status = "cancelled"
        job.finished_at = utcnow()
        await self.cleanup_files(job)
        await self.session.commit()
        return WorkflowCancelResponse(job_id=job.job_id, status=job.status)

    async def _get_by_job_id(self, job_id: str) -> WorkflowJob | None:
        return await self.session.scalar(select(WorkflowJob).where(WorkflowJob.job_id == job_id))

    async def _get_by_idempotency_key(self, idempotency_key: str | None) -> WorkflowJob | None:
        if not idempotency_key:
            return None
        return await self.session.scalar(select(WorkflowJob).where(WorkflowJob.idempotency_key == idempotency_key))

    async def _enforce_owner_concurrency(self, owner_id: str) -> None:
        count = await self.session.scalar(
            select(func.count())
            .select_from(WorkflowJob)
            .where(WorkflowJob.owner_id == owner_id, WorkflowJob.status.in_(ACTIVE_STATUSES))
        )
        if count and count >= self.settings.workflow_gateway_max_concurrent_jobs_per_owner:
            raise HTTPException(status_code=429, detail="Too many active workflow jobs for owner")

    def _build_job(
        self,
        *,
        source_type: str,
        owner_id: str,
        access_scope: str,
        inputs: dict[str, Any],
        idempotency_key: str | None,
        manifest: list[dict[str, Any]],
    ) -> WorkflowJob:
        job_id = f"wjob_{secrets.token_urlsafe(18).replace('-', '_')}"
        return WorkflowJob(
            job_id=job_id,
            idempotency_key=idempotency_key,
            source_type=source_type,
            status="queued",
            owner_id=owner_id,
            access_scope=access_scope,
            dify_user=owner_id,
            request_inputs_json=inputs,
            temporary_file_manifest_json=manifest,
            expires_at=utcnow() + timedelta(days=self.settings.workflow_gateway_result_retention_days),
        )

    async def _store_uploads(self, *, paper_file: UploadFile, supplementary_images: list[UploadFile]) -> list[dict[str, Any]]:
        upload_dir = Path(self.settings.workflow_gateway_upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        manifest = [
            await self._store_one_file(
                upload_dir=upload_dir,
                upload=paper_file,
                allowed_extensions=DOCUMENT_EXTENSIONS,
                allowed_mime=DOCUMENT_MIME_PREFIXES,
                kind="paper_file",
            )
        ]
        for image in supplementary_images:
            manifest.append(
                await self._store_one_file(
                    upload_dir=upload_dir,
                    upload=image,
                    allowed_extensions=IMAGE_EXTENSIONS,
                    allowed_mime=IMAGE_MIME_PREFIXES,
                    kind="supplementary_image",
                )
            )
        return manifest

    async def _store_one_file(
        self,
        *,
        upload_dir: Path,
        upload: UploadFile,
        allowed_extensions: set[str],
        allowed_mime: set[str],
        kind: str,
    ) -> dict[str, Any]:
        if not upload.filename:
            raise HTTPException(status_code=422, detail=f"{kind} filename is required")
        original_name = Path(upload.filename).name
        extension = Path(original_name).suffix.lower()
        if extension not in allowed_extensions:
            raise HTTPException(status_code=422, detail=f"{kind} extension is not allowed")
        content_type = upload.content_type or mimetypes.guess_type(original_name)[0] or "application/octet-stream"
        if content_type not in allowed_mime:
            raise HTTPException(status_code=422, detail=f"{kind} MIME type is not allowed")
        content = await upload.read()
        max_bytes = self.settings.workflow_gateway_max_upload_mb * 1024 * 1024
        if not content:
            raise HTTPException(status_code=422, detail=f"{kind} must not be empty")
        if len(content) > max_bytes:
            raise HTTPException(status_code=413, detail=f"{kind} exceeds upload size limit")
        _validate_magic(content, extension, kind)
        stored_name = f"{secrets.token_urlsafe(24)}{extension}"
        path = upload_dir / stored_name
        path.write_bytes(content)
        return {
            "kind": kind,
            "path": str(path),
            "original_filename": original_name,
            "content_type": content_type,
            "size": len(content),
            "uploaded_file_id": None,
        }

    async def cleanup_files(self, job: WorkflowJob) -> None:
        for item in job.temporary_file_manifest_json or []:
            path = Path(str(item.get("path", "")))
            try:
                if path.is_file():
                    path.unlink()
            except OSError:
                pass
        job.temporary_file_manifest_json = []

    @staticmethod
    def _can_access(job: WorkflowJob, client: ApiClient) -> bool:
        if client.is_admin:
            return True
        if job.access_scope == "public":
            return True
        if job.access_scope == "shared":
            return bool(client.owner_id)
        return bool(client.owner_id and client.owner_id == job.owner_id)

    @staticmethod
    def to_status_read(job: WorkflowJob) -> WorkflowJobStatusRead:
        error = None
        if job.error_code or job.error_message:
            error = {"code": job.error_code, "message": job.error_message}
        return WorkflowJobStatusRead(
            job_id=job.job_id,
            status=job.status,
            source_type=job.source_type,
            owner_id=job.owner_id,
            access_scope=job.access_scope,
            current_node_id=job.current_node_id,
            current_node_title=job.current_node_title,
            event_count=job.event_count,
            dify_workflow_run_id=job.dify_workflow_run_id,
            dify_task_id=job.dify_task_id,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            error=error,
        )

    @staticmethod
    def _accepted(job: WorkflowJob) -> WorkflowJobAccepted:
        return WorkflowJobAccepted(
            job_id=job.job_id,
            status=job.status,
            status_url=f"/v1/workflow-jobs/{job.job_id}",
            result_url=f"/v1/workflow-jobs/{job.job_id}/result",
        )


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def _validate_magic(content: bytes, extension: str, kind: str) -> None:
    lowered = content[:16].lower()
    if extension == ".pdf" and not content.startswith(b"%PDF"):
        raise HTTPException(status_code=422, detail=f"{kind} file header does not match PDF")
    if extension == ".docx" and not content.startswith(b"PK"):
        raise HTTPException(status_code=422, detail=f"{kind} file header does not match DOCX")
    if extension == ".png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(status_code=422, detail=f"{kind} file header does not match PNG")
    if extension in {".jpg", ".jpeg"} and not content.startswith(b"\xff\xd8\xff"):
        raise HTTPException(status_code=422, detail=f"{kind} file header does not match JPEG")
    if extension == ".webp" and not (content.startswith(b"RIFF") and content[8:12] == b"WEBP"):
        raise HTTPException(status_code=422, detail=f"{kind} file header does not match WEBP")
    if extension in {".txt", ".md"} and b"\x00" in lowered:
        raise HTTPException(status_code=422, detail=f"{kind} file appears to be binary")


class WorkflowJobRunner:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def run(self, job_id: str) -> None:
        job = await self._get(job_id)
        if job is None or job.status in FINAL_STATUSES:
            return
        if job.status == "cancel_requested":
            await self._mark_cancelled(job)
            return
        provider = DifyWorkflowProvider(self.settings)
        try:
            if job.dify_workflow_run_id:
                await self.recover(job, provider)
            else:
                await self._start_new_run(job, provider)
        except Exception as exc:
            await self._handle_runtime_error(job, provider, exc)
        finally:
            await provider.close()

    async def recover_unfinished(self) -> int:
        result = await self.session.scalars(select(WorkflowJob).where(WorkflowJob.status.in_(ACTIVE_STATUSES)))
        count = 0
        for job in result:
            if job.status in FINAL_STATUSES:
                continue
            count += 1
            await self.run(job.job_id)
        return count

    async def _start_new_run(self, job: WorkflowJob, provider: DifyWorkflowProvider) -> None:
        if not self.settings.dify_workflow_api_key:
            await self._mark_failed(job, "missing_dify_workflow_api_key", "Dify workflow API key is not configured")
            return
        await self._upload_files(job, provider)
        job.status = "starting"
        job.updated_at = utcnow()
        await self.session.commit()
        await self._run_workflow_with_start_retries(job, provider)

    async def _run_workflow_with_start_retries(self, job: WorkflowJob, provider: DifyWorkflowProvider) -> None:
        max_attempts = max(1, self.settings.workflow_gateway_start_max_attempts)
        last_error: Exception | None = None
        async with asyncio.timeout(self.settings.workflow_gateway_max_runtime_seconds):
            for attempt in range(max_attempts):
                try:
                    async for event in provider.run_workflow(inputs=job.request_inputs_json, user=job.dify_user):
                        await self.apply_event(job, event)
                        await self.session.commit()
                        if job.status in FINAL_STATUSES:
                            return
                    return
                except Exception as exc:
                    last_error = exc
                    if job.dify_workflow_run_id or job.dify_task_id or job.event_count > 0:
                        raise
                    if attempt >= max_attempts - 1:
                        break
                    delay = self.settings.workflow_gateway_reconnect_base_delay_seconds * (2**attempt)
                    await asyncio.sleep(min(delay, 30) + random.uniform(0, 1))
                    job.status = "starting"
                    job.updated_at = utcnow()
                    await self.session.commit()
        if last_error is not None:
            raise last_error

    async def _upload_files(self, job: WorkflowJob, provider: DifyWorkflowProvider) -> None:
        manifest = list(job.temporary_file_manifest_json or [])
        if not manifest:
            return
        job.status = "uploading"
        await self.session.commit()
        inputs = dict(job.request_inputs_json)
        images: list[dict[str, str]] = []
        changed_manifest: list[dict[str, Any]] = []
        for item in manifest:
            item = dict(item)
            upload_id = item.get("uploaded_file_id")
            if not upload_id:
                upload_id = await provider.upload_file(
                    path=Path(item["path"]),
                    user=job.dify_user,
                    file_type="image" if item["kind"] == "supplementary_image" else "document",
                    mime_type=item["content_type"],
                )
                item["uploaded_file_id"] = upload_id
            file_object = {
                "type": "image" if item["kind"] == "supplementary_image" else "document",
                "transfer_method": "local_file",
                "upload_file_id": upload_id,
            }
            if item["kind"] == "paper_file":
                inputs["paper_file"] = file_object
                job.dify_upload_file_id = upload_id
            else:
                images.append(file_object)
            changed_manifest.append(item)
        inputs["supplementary_images"] = images
        job.request_inputs_json = inputs
        job.temporary_file_manifest_json = changed_manifest
        await self.session.commit()

    async def apply_event(self, job: WorkflowJob, event: dict[str, Any]) -> None:
        name = event.get("event") or event.get("type")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        if name in {None, "ping"}:
            return
        job.event_count += 1
        job.updated_at = utcnow()
        if name == "workflow_started":
            job.status = "running"
            job.started_at = job.started_at or utcnow()
            job.dify_task_id = str(event.get("task_id") or data.get("task_id") or job.dify_task_id or "")
            run_id = event.get("workflow_run_id") or data.get("workflow_run_id") or data.get("id")
            job.dify_workflow_run_id = str(run_id or job.dify_workflow_run_id or "")
        elif name in {"node_started", "node_retry", "iteration_started", "iteration_next"}:
            job.status = "running"
            job.current_node_id = _as_optional_str(data.get("node_id") or data.get("id") or event.get("node_id"))
            job.current_node_title = _as_optional_str(
                data.get("title") or data.get("node_title") or data.get("node_name") or event.get("node_title")
            )
        elif name in {"node_finished", "iteration_completed"}:
            job.current_node_id = _as_optional_str(data.get("node_id") or data.get("id") or job.current_node_id)
            job.current_node_title = _as_optional_str(data.get("title") or data.get("node_title") or job.current_node_title)
        elif name == "workflow_finished":
            await self._apply_finished_event(job, data)
        elif name == "error":
            await self._mark_failed(job, _as_optional_str(data.get("error_code") or event.get("code")), _event_error_message(event, data))

    async def _apply_finished_event(self, job: WorkflowJob, data: dict[str, Any]) -> None:
        status_value = str(data.get("status") or "succeeded").lower()
        if status_value in {"succeeded", "success", "completed"}:
            outputs = data.get("outputs") or {}
            job.result_json = outputs if isinstance(outputs, dict) else {"outputs": outputs}
            job.result_summary_json = self._summarize_result(job.result_json, job)
            job.status = "succeeded"
            job.finished_at = utcnow()
            await WorkflowGatewayService(self.session, self.settings).cleanup_files(job)
        elif status_value in {"stopped", "cancelled", "canceled"}:
            await self._mark_cancelled(job)
        else:
            await self._mark_failed(job, _as_optional_str(data.get("error_code")), _as_optional_str(data.get("error")) or "Workflow failed")

    async def recover(self, job: WorkflowJob, provider: DifyWorkflowProvider) -> None:
        job.status = "reconnecting"
        job.retry_count += 1
        await self.session.commit()
        if job.dify_task_id:
            for event in await provider.recover_events(task_id=job.dify_task_id, user=job.dify_user):
                await self.apply_event(job, event)
                await self.session.commit()
                if job.status in FINAL_STATUSES:
                    return
        if job.dify_workflow_run_id:
            detail = await provider.get_run_detail(workflow_run_id=job.dify_workflow_run_id)
            await self.apply_run_detail(job, detail)
            await self.session.commit()

    async def apply_run_detail(self, job: WorkflowJob, detail: dict[str, Any]) -> None:
        data = detail.get("data") if isinstance(detail.get("data"), dict) else detail
        status_value = str(data.get("status") or "").lower()
        if status_value in {"succeeded", "success", "completed"}:
            outputs = data.get("outputs") or {}
            job.result_json = outputs if isinstance(outputs, dict) else {"outputs": outputs}
            job.result_summary_json = self._summarize_result(job.result_json, job)
            job.status = "succeeded"
            job.finished_at = utcnow()
            await WorkflowGatewayService(self.session, self.settings).cleanup_files(job)
        elif status_value in {"failed", "error"}:
            await self._mark_failed(job, _as_optional_str(data.get("error_code")), _as_optional_str(data.get("error")) or "Workflow failed")
        elif status_value in {"stopped", "cancelled", "canceled"}:
            await self._mark_cancelled(job)
        else:
            job.status = "reconnecting"

    async def _handle_runtime_error(self, job: WorkflowJob, provider: DifyWorkflowProvider, exc: Exception) -> None:
        if job.dify_workflow_run_id or job.dify_task_id:
            for attempt in range(self.settings.workflow_gateway_reconnect_max_attempts):
                try:
                    if attempt:
                        delay = self.settings.workflow_gateway_reconnect_base_delay_seconds * (2 ** (attempt - 1))
                        await asyncio.sleep(min(delay, 60) + random.uniform(0, 1))
                    await self.recover(job, provider)
                    if job.status in FINAL_STATUSES:
                        return
                except Exception:
                    continue
        code = "workflow_runtime_error"
        if job.event_count == 0 and not job.dify_workflow_run_id and not job.dify_task_id:
            code = "workflow_start_error"
        await self._mark_failed(job, code, str(exc))
        await self.session.commit()

    async def _mark_failed(self, job: WorkflowJob, code: str | None, message: str | None) -> None:
        job.status = "failed"
        job.error_code = code or "workflow_failed"
        job.error_message = message or "Workflow failed"
        job.finished_at = utcnow()
        await WorkflowGatewayService(self.session, self.settings).cleanup_files(job)

    async def _mark_cancelled(self, job: WorkflowJob) -> None:
        job.status = "cancelled"
        job.finished_at = utcnow()
        await WorkflowGatewayService(self.session, self.settings).cleanup_files(job)
        await self.session.commit()

    async def _get(self, job_id: str) -> WorkflowJob | None:
        return await self.session.scalar(select(WorkflowJob).where(WorkflowJob.job_id == job_id))

    @staticmethod
    def _summarize_result(result: dict[str, Any], job: WorkflowJob) -> dict[str, Any]:
        paper_result = result.get("paper_result") if isinstance(result.get("paper_result"), dict) else result
        return {
            "title": paper_result.get("title") or paper_result.get("paper_title"),
            "status": "succeeded",
            "message": paper_result.get("message") or "Workflow completed",
            "analysis_id": paper_result.get("analysis_id") or job.request_inputs_json.get("analysis_id"),
            "summary": paper_result.get("summary") or paper_result.get("one_sentence_summary"),
            "contributions": paper_result.get("contributions"),
            "limitations": paper_result.get("limitations"),
            "workflow_run_id": job.dify_workflow_run_id,
            "elapsed_time": paper_result.get("elapsed_time"),
        }


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _event_error_message(event: dict[str, Any], data: dict[str, Any]) -> str:
    message = data.get("error") or data.get("message") or event.get("message") or event.get("error")
    return str(message or "Workflow error")
