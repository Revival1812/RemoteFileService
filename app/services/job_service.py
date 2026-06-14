import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.base import utcnow
from app.models.graph_sync_record import GraphSyncRecord
from app.providers.dify_knowledge import DifyKnowledgeProvider
from app.providers.disabled import DisabledGraphProvider, DisabledKnowledgeProvider, DisabledObjectStorageProvider
from app.providers.neo4j_graph import Neo4jGraphProvider
from app.providers.object_storage import ObjectStorageProviderImpl
from app.repositories.jobs import JobRepository
from app.repositories.papers import PaperRepository

logger = logging.getLogger(__name__)


class JobService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def sync_job(self, job_id: str) -> None:
        job_uuid = uuid.UUID(job_id)
        async with self.session.begin():
            job = await JobRepository(self.session).get(job_uuid)
            if job is None:
                raise ValueError("job not found")
            if job.dedup_status == "existing":
                job.status = "completed"
                job.completed_at = utcnow()
                return
            paper = await PaperRepository(self.session).get_by_uuid(job.paper_id)
            version = await PaperRepository(self.session).latest_version(job.paper_id)
            if paper is None or version is None:
                raise ValueError("paper or version not found")
            job.status = "syncing"

        kb_result_status = job.kb_status
        graph_result_status = job.graph_status
        error_messages: list[str] = []

        async with self.session.begin():
            job = await JobRepository(self.session).get(job_uuid)
            paper = await PaperRepository(self.session).get_by_uuid(job.paper_id)
            version = await PaperRepository(self.session).latest_version(job.paper_id)
            kb_provider = self._knowledge_provider()
            kb_result = await kb_provider.sync_documents(session=self.session, paper=paper, version=version, job=job)
            if hasattr(kb_provider, "close"):
                await kb_provider.close()
            kb_result_status = kb_result.status
            if kb_result.status == "failed":
                error_messages.append(f"dify: {kb_result.message}")
            job.kb_status = kb_result.status

        async with self.session.begin():
            job = await JobRepository(self.session).get(job_uuid)
            paper = await PaperRepository(self.session).get_by_uuid(job.paper_id)
            version = await PaperRepository(self.session).latest_version(job.paper_id)
            graph_provider = self._graph_provider()
            graph_result = await graph_provider.sync_graph(session=self.session, paper=paper, version=version, job=job)
            if hasattr(graph_provider, "close"):
                await graph_provider.close()
            graph_result_status = graph_result.status
            if graph_result.status == "failed":
                error_messages.append(f"neo4j: {graph_result.message}")
            job.graph_status = graph_result.status
            if graph_result.status in {"completed", "failed"}:
                record = await self.session.scalar(
                    select(GraphSyncRecord).where(
                        GraphSyncRecord.paper_id == paper.id,
                        GraphSyncRecord.content_hash == version.content_hash,
                    )
                )
                if record is None:
                    record = GraphSyncRecord(paper_id=paper.id, content_hash=version.content_hash)
                    self.session.add(record)
                record.node_count = graph_result.metadata.get("node_count", 0)
                record.edge_count = graph_result.metadata.get("edge_count", 0)
                record.sync_status = graph_result.status
                record.error_message = graph_result.message if graph_result.status == "failed" else None

        async with self.session.begin():
            job = await JobRepository(self.session).get(job_uuid)
            final_statuses = {kb_result_status, graph_result_status}
            if "failed" in final_statuses and ("completed" in final_statuses or "skipped" in final_statuses or "disabled" in final_statuses):
                job.status = "partial_success"
            elif final_statuses == {"failed"}:
                job.status = "failed"
            else:
                job.status = "completed"
            job.error_message = "; ".join(error_messages) or None
            job.completed_at = utcnow()

    async def retry(self, job_id: str) -> None:
        async with self.session.begin():
            job = await JobRepository(self.session).get(uuid.UUID(job_id))
            if job is None:
                raise ValueError("job not found")
            job.retry_count += 1
            job.status = "received"
            job.error_message = None

    def _knowledge_provider(self):
        if self.settings.enable_dify_sync and self.settings.dify_kb_api_key:
            return DifyKnowledgeProvider(self.settings)
        return DisabledKnowledgeProvider()

    def _graph_provider(self):
        if self.settings.enable_neo4j_sync and self.settings.neo4j_password:
            return Neo4jGraphProvider(self.settings)
        return DisabledGraphProvider()

    def _storage_provider(self):
        if self.settings.enable_object_storage:
            return ObjectStorageProviderImpl(self.settings)
        return DisabledObjectStorageProvider()
