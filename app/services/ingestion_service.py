import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.base import utcnow
from app.models.ingestion_job import IngestionJob
from app.models.paper import Paper
from app.models.paper_version import PaperVersion
from app.repositories.jobs import JobRepository
from app.repositories.papers import PaperRepository
from app.schemas.ingestion import IngestionAcceptedResponse, IngestionJobCreate
from app.services.deduplication_service import DeduplicationService, normalize_title
from app.workers.tasks import dispatch_sync_job

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    job: IngestionJob
    paper: Paper
    version: PaperVersion | None
    should_sync: bool
    warnings: list[str] = field(default_factory=list)


class IngestionService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def submit(self, payload: IngestionJobCreate) -> IngestionAcceptedResponse:
        result: IngestionResult | None = None
        for attempt in range(5):
            try:
                result = await self._register(payload)
                await self.session.commit()
                break
            except IntegrityError:
                await self.session.rollback()
                logger.info("Retrying ingestion registration after unique constraint conflict")
                await asyncio.sleep(0.05 * (attempt + 1))
            except OperationalError as exc:
                await self.session.rollback()
                if "database is locked" not in str(exc).lower() or attempt == 4:
                    raise
                await asyncio.sleep(0.05 * (attempt + 1))
        if result is None:
            result = await self._register(payload)
            await self.session.commit()
        if result.should_sync:
            await dispatch_sync_job(str(result.job.job_id), self.settings)
        return IngestionAcceptedResponse(
            accepted=True,
            job_id=str(result.job.job_id),
            paper_id=result.paper.paper_id,
            dedup_status=result.job.dedup_status,
            kb_status=result.job.kb_status,
            graph_status=result.job.graph_status,
            warnings=result.warnings,
        )

    async def _register(self, payload: IngestionJobCreate) -> IngestionResult:
        async with self.session.begin_nested():
            await self._advisory_lock(payload.paper_id)
            papers = PaperRepository(self.session)
            dedupe = DeduplicationService(self.session)
            paper = await papers.get_by_public_id(payload.paper_id, for_update=True)
            title = self._extract_title(payload.profile)
            normalized_title = normalize_title(title)
            source = payload.source_metadata.model_dump()

            if paper is None:
                paper = Paper(
                    paper_id=payload.paper_id,
                    canonical_title=title,
                    normalized_title=normalized_title,
                    doi=source.get("doi") or None,
                    arxiv_id=source.get("arxiv_id") or self._extract_arxiv_id(payload.paper_id),
                    authors_json=self._extract_authors(payload.profile),
                    year=self._extract_year(payload.profile),
                    latest_content_hash=payload.content_hash,
                    latest_version=1,
                    status="active",
                )
                self.session.add(paper)
                await self.session.flush()
                version = self._new_version(paper=paper, version_number=1, payload=payload)
                self.session.add(version)
                job = self._new_job(paper=paper, payload=payload, dedup_status="new", should_sync=True)
                self.session.add(job)
                warnings = await self._possible_duplicate_warning(dedupe, payload.paper_id, normalized_title)
                return IngestionResult(job=job, paper=paper, version=version, should_sync=True, warnings=warnings)

            if paper.latest_content_hash == payload.content_hash:
                paper.last_seen_at = utcnow()
                prior_job = await JobRepository(self.session).by_paper_hash(paper.id, payload.content_hash)
                job = self._new_job(paper=paper, payload=payload, dedup_status="existing", should_sync=False)
                job.status = "completed"
                job.kb_status = prior_job.kb_status if prior_job else "skipped"
                job.graph_status = prior_job.graph_status if prior_job else "skipped"
                self.session.add(job)
                latest_version = await papers.latest_version(paper.id)
                return IngestionResult(job=job, paper=paper, version=latest_version, should_sync=False)

            version_number = paper.latest_version + 1
            paper.latest_content_hash = payload.content_hash
            paper.latest_version = version_number
            if title and not paper.canonical_title:
                paper.canonical_title = title
                paper.normalized_title = normalized_title
            version = self._new_version(paper=paper, version_number=version_number, payload=payload)
            job = self._new_job(paper=paper, payload=payload, dedup_status="new_version", should_sync=True)
            self.session.add_all([version, job])
            return IngestionResult(job=job, paper=paper, version=version, should_sync=True)

    async def _advisory_lock(self, paper_id: str) -> None:
        bind = self.session.bind
        if bind is not None and bind.dialect.name == "postgresql":
            await self.session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:paper_id, 0))"), {"paper_id": paper_id})

    async def _possible_duplicate_warning(
        self, dedupe: DeduplicationService, paper_id: str, normalized_title: str | None
    ) -> list[str]:
        match = await dedupe.find_possible_duplicate(paper_id=paper_id, normalized_title=normalized_title)
        if match is None:
            return []
        other_id, score = match
        await dedupe.create_candidate(
            paper_id_a=paper_id,
            paper_id_b=other_id,
            score=score,
            reason="normalized_title_similarity",
        )
        return [f"possible duplicate of {other_id} with title similarity {score:.3f}"]

    def _new_version(self, *, paper: Paper, version_number: int, payload: IngestionJobCreate) -> PaperVersion:
        return PaperVersion(
            paper_id=paper.id,
            version_number=version_number,
            content_hash=payload.content_hash,
            profile_json=payload.profile,
            graph_json=payload.graph.model_dump(mode="json") if payload.graph else None,
            source_metadata_json=payload.source_metadata.model_dump(mode="json"),
            knowledge_documents_json=[doc.model_dump(mode="json") for doc in payload.knowledge_documents],
        )

    def _new_job(self, *, paper: Paper, payload: IngestionJobCreate, dedup_status: str, should_sync: bool) -> IngestionJob:
        kb_status = "pending" if should_sync and self.settings.enable_dify_sync and payload.knowledge_documents else "disabled"
        if should_sync and not payload.knowledge_documents:
            kb_status = "skipped"
        graph_status = "pending" if should_sync and self.settings.enable_neo4j_sync and payload.graph else "disabled"
        if should_sync and payload.graph is None:
            graph_status = "skipped"
        return IngestionJob(
            paper_id=paper.id,
            content_hash=payload.content_hash,
            status="received",
            dedup_status=dedup_status,
            kb_status=kb_status,
            graph_status=graph_status,
            storage_status="disabled",
            request_schema_version=payload.schema_version,
        )

    @staticmethod
    def _extract_title(profile: dict[str, Any]) -> str | None:
        title = profile.get("title") or profile.get("paper_title")
        return str(title).strip() if title else None

    @staticmethod
    def _extract_authors(profile: dict[str, Any]) -> dict[str, Any] | None:
        authors = profile.get("authors")
        if authors is None:
            return None
        return {"authors": authors}

    @staticmethod
    def _extract_year(profile: dict[str, Any]) -> int | None:
        year = profile.get("year")
        try:
            return int(year) if year is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_arxiv_id(paper_id: str) -> str | None:
        return paper_id.split(":", 1)[1] if paper_id.startswith("arxiv:") else None
