import asyncio
import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.kb_document import KbDocument
from app.providers.base import ProviderResult, elapsed_timer

logger = logging.getLogger(__name__)


class DifyKnowledgeProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        timeout = httpx.Timeout(
            connect=settings.provider_connect_timeout_seconds,
            read=settings.provider_read_timeout_seconds,
            write=settings.provider_read_timeout_seconds,
            pool=settings.provider_connect_timeout_seconds,
        )
        self.client = httpx.AsyncClient(
            base_url=settings.dify_api_base_url.rstrip("/"),
            timeout=timeout,
            headers={"Authorization": f"Bearer {settings.dify_kb_api_key}"},
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def _request_with_retry(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self.settings.max_retry_count + 1):
            try:
                response = await self.client.request(method, url, **kwargs)
                if response.status_code not in {429, 500, 502, 503, 504}:
                    response.raise_for_status()
                    return response
                response.raise_for_status()
            except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt >= self.settings.max_retry_count:
                    break
                await asyncio.sleep(min(2**attempt, 8))
        raise RuntimeError("Dify request failed after retries") from last_error

    async def sync_documents(self, *, session: AsyncSession, paper: Any, version: Any, job: Any) -> ProviderResult:
        if not self.settings.dify_papers_dataset_id:
            return ProviderResult(provider="dify", status="disabled", message="missing dataset id")
        documents = version.knowledge_documents_json or []
        if not documents:
            return ProviderResult(provider="dify", status="skipped", message="no knowledge documents")
        with elapsed_timer() as timer:
            try:
                synced = 0
                for document in documents:
                    await self._sync_one(session=session, paper=paper, version=version, document=document)
                    synced += 1
                await session.flush()
                return ProviderResult(
                    provider="dify",
                    status="completed",
                    message=f"synced {synced} documents",
                    elapsed_ms=timer.elapsed_ms,
                    metadata={"document_count": synced},
                )
            except Exception as exc:
                logger.exception("Dify sync failed", extra={"extra_fields": {"provider": "dify"}})
                return ProviderResult(provider="dify", status="failed", message=str(exc), elapsed_ms=timer.elapsed_ms)

    async def _sync_one(self, *, session: AsyncSession, paper: Any, version: Any, document: dict[str, Any]) -> None:
        document_key = document["document_key"]
        existing = await session.scalar(select(KbDocument).where(KbDocument.document_key == document_key))
        if existing is not None and existing.content_hash == version.content_hash:
            return

        payload = {
            "name": document["name"],
            "text": document["content"],
            "indexing_technique": self.settings.dify_indexing_technique,
            "process_rule": {"mode": "automatic"},
            "doc_form": "text_model",
            "doc_language": "English",
        }
        dataset_id = self.settings.dify_papers_dataset_id
        if existing is None:
            response = await self._request_with_retry("POST", f"/datasets/{dataset_id}/document/create_by_text", json=payload)
        else:
            response = await self._request_with_retry(
                "POST",
                f"/datasets/{dataset_id}/documents/{existing.remote_document_id}/update_by_text",
                json=payload,
            )
        body = response.json()
        document_id = body.get("document", {}).get("id") or body.get("id")
        batch_id = body.get("batch")
        indexing_status = await self._poll_indexing_status(dataset_id=dataset_id, batch_id=batch_id, document_id=document_id)

        metadata = dict(document.get("metadata") or {})
        metadata.setdefault("paper_id", paper.paper_id)
        metadata.setdefault("content_hash", version.content_hash)
        metadata.setdefault("version", version.version_number)
        metadata.setdefault("status", indexing_status)

        if existing is None:
            session.add(
                KbDocument(
                    document_key=document_key,
                    paper_id=paper.id,
                    content_hash=version.content_hash,
                    provider="dify",
                    dataset_id=dataset_id,
                    remote_document_id=document_id,
                    batch_id=batch_id,
                    indexing_status=indexing_status,
                    metadata_json=metadata,
                )
            )
        else:
            existing.content_hash = version.content_hash
            existing.remote_document_id = document_id or existing.remote_document_id
            existing.batch_id = batch_id
            existing.indexing_status = indexing_status
            existing.metadata_json = metadata

    async def _poll_indexing_status(self, *, dataset_id: str, batch_id: str | None, document_id: str | None) -> str:
        if not batch_id:
            return "unknown"
        deadline = asyncio.get_running_loop().time() + self.settings.dify_index_timeout_seconds
        while True:
            response = await self._request_with_retry("GET", f"/datasets/{dataset_id}/documents/{batch_id}/indexing-status")
            body = response.json()
            statuses = body.get("data") or body.get("statuses") or []
            status = None
            if isinstance(statuses, list) and statuses:
                match = next((item for item in statuses if item.get("document_id") == document_id), statuses[0])
                status = match.get("indexing_status") or match.get("status")
            elif isinstance(body, dict):
                status = body.get("indexing_status") or body.get("status")
            if status in {"completed", "error", "failed"}:
                return "completed" if status == "completed" else "error"
            if asyncio.get_running_loop().time() >= deadline:
                return "timeout"
            await asyncio.sleep(self.settings.dify_poll_interval_seconds)

    async def validate_dataset(self) -> bool:
        if not self.settings.dify_papers_dataset_id:
            return False
        response = await self._request_with_retry("GET", f"/datasets/{self.settings.dify_papers_dataset_id}")
        return response.status_code < 400

    async def ensure_metadata_fields(self) -> list[str]:
        fields = [
            "paper_id",
            "content_hash",
            "content_type",
            "section_id",
            "section_title",
            "title",
            "arxiv_id",
            "doi",
            "year",
            "subdomain",
            "origin",
            "owner_id",
            "access_scope",
            "version",
            "status",
        ]
        # Dify deployments differ in metadata APIs. This bootstrap validates access and returns desired fields.
        await self.validate_dataset()
        return fields

