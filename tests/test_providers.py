

from app.core.config import Settings
from app.models.ingestion_job import IngestionJob
from app.models.paper import Paper
from app.models.paper_version import PaperVersion
from app.providers.base import ProviderResult
from app.providers.dify_knowledge import DifyKnowledgeProvider
from app.providers.disabled import DisabledGraphProvider, DisabledKnowledgeProvider
from app.providers.neo4j_graph import Neo4jGraphProvider
from app.services.job_service import JobService


async def test_disabled_dify_provider(db_session):
    result = await DisabledKnowledgeProvider().sync_documents(session=db_session, paper=None, version=None, job=None)
    assert result.status == "disabled"


async def test_disabled_neo4j_provider(db_session):
    result = await DisabledGraphProvider().sync_graph(session=db_session, paper=None, version=None, job=None)
    assert result.status == "disabled"


async def test_mocked_dify_create_document(httpx_mock, db_session):
    settings = Settings(
        dify_api_base_url="https://dify.test",
        dify_kb_api_key="secret",
        dify_papers_dataset_id="ds",
        dify_poll_interval_seconds=0,
    )
    httpx_mock.add_response(
        method="POST",
        url="https://dify.test/datasets/ds/document/create_by_text",
        json={"document": {"id": "doc-1"}, "batch": "batch-1"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://dify.test/datasets/ds/documents/batch-1/indexing-status",
        json={"data": [{"document_id": "doc-1", "indexing_status": "completed"}]},
    )
    paper, version, job = await _seed_paper(db_session)
    provider = DifyKnowledgeProvider(settings)
    try:
        result = await provider.sync_documents(session=db_session, paper=paper, version=version, job=job)
    finally:
        await provider.close()
    assert result.status == "completed"


async def test_mocked_dify_update_document(httpx_mock, db_session):
    settings = Settings(
        dify_api_base_url="https://dify.test",
        dify_kb_api_key="secret",
        dify_papers_dataset_id="ds",
        dify_poll_interval_seconds=0,
    )
    paper, version, job = await _seed_paper(db_session)
    provider = DifyKnowledgeProvider(settings)
    httpx_mock.add_response(
        method="POST",
        url="https://dify.test/datasets/ds/document/create_by_text",
        json={"document": {"id": "doc-1"}, "batch": "batch-1"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://dify.test/datasets/ds/documents/batch-1/indexing-status",
        json={"data": [{"document_id": "doc-1", "indexing_status": "completed"}]},
    )
    await provider.sync_documents(session=db_session, paper=paper, version=version, job=job)
    version.content_hash = "b" * 64
    httpx_mock.add_response(
        method="POST",
        url="https://dify.test/datasets/ds/documents/doc-1/update_by_text",
        json={"document": {"id": "doc-1"}, "batch": "batch-2"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://dify.test/datasets/ds/documents/batch-2/indexing-status",
        json={"data": [{"document_id": "doc-1", "indexing_status": "completed"}]},
    )
    try:
        result = await provider.sync_documents(session=db_session, paper=paper, version=version, job=job)
    finally:
        await provider.close()
    assert result.status == "completed"


async def test_mocked_dify_indexing_completed(httpx_mock):
    settings = Settings(dify_api_base_url="https://dify.test", dify_kb_api_key="secret", dify_papers_dataset_id="ds", dify_poll_interval_seconds=0)
    httpx_mock.add_response(
        method="GET",
        url="https://dify.test/datasets/ds/documents/batch/indexing-status",
        json={"data": [{"document_id": "doc", "indexing_status": "completed"}]},
    )
    provider = DifyKnowledgeProvider(settings)
    try:
        assert await provider._poll_indexing_status(dataset_id="ds", batch_id="batch", document_id="doc") == "completed"
    finally:
        await provider.close()


async def test_mocked_dify_indexing_error(httpx_mock):
    settings = Settings(dify_api_base_url="https://dify.test", dify_kb_api_key="secret", dify_papers_dataset_id="ds", dify_poll_interval_seconds=0)
    httpx_mock.add_response(
        method="GET",
        url="https://dify.test/datasets/ds/documents/batch/indexing-status",
        json={"data": [{"document_id": "doc", "indexing_status": "error"}]},
    )
    provider = DifyKnowledgeProvider(settings)
    try:
        assert await provider._poll_indexing_status(dataset_id="ds", batch_id="batch", document_id="doc") == "error"
    finally:
        await provider.close()


async def test_mocked_neo4j_upsert():
    class FakeTx:
        def __init__(self):
            self.calls = 0

        async def run(self, *_args, **_kwargs):
            self.calls += 1

    tx = FakeTx()
    await Neo4jGraphProvider._upsert_graph(tx, [{"uid": "a", "name": "A", "type": "T"}], [])
    assert tx.calls == 2


async def test_dify_success_neo4j_failure_partial_success(monkeypatch, db_session):
    paper, version, job = await _seed_paper(db_session)
    await db_session.commit()

    class FakeKb:
        async def sync_documents(self, **_kwargs):
            return ProviderResult(provider="dify", status="completed")

    class FakeGraph:
        async def sync_graph(self, **_kwargs):
            return ProviderResult(provider="neo4j", status="failed", message="boom")

    monkeypatch.setattr(JobService, "_knowledge_provider", lambda self: FakeKb())
    monkeypatch.setattr(JobService, "_graph_provider", lambda self: FakeGraph())
    await JobService(db_session, Settings(enable_dify_sync=True, enable_neo4j_sync=True)).sync_job(str(job.job_id))
    await db_session.refresh(job)
    assert job.status == "partial_success"
    assert job.kb_status == "completed"
    assert job.graph_status == "failed"


async def _seed_paper(db_session):
    paper = Paper(paper_id="arxiv:seed", latest_content_hash="a" * 64, latest_version=1, status="active")
    db_session.add(paper)
    await db_session.flush()
    version = PaperVersion(
        paper_id=paper.id,
        version_number=1,
        content_hash="a" * 64,
        profile_json={"title": "Seed"},
        graph_json={
            "paper_id": "arxiv:seed",
            "nodes": [{"uid": "a", "name": "A", "type": "Method"}, {"uid": "b", "name": "B", "type": "Dataset"}],
            "edges": [{"source_uid": "a", "target_uid": "b", "relation": "USES", "evidence": "A uses B.", "confidence": 1.0}],
        },
        source_metadata_json={"access_scope": "private"},
        knowledge_documents_json=[
            {
                "document_key": "arxiv:seed:profile",
                "name": "Seed Profile",
                "content": "Seed content",
                "metadata": {"content_type": "paper_profile"},
            }
        ],
    )
    job = IngestionJob(
        paper_id=paper.id,
        content_hash="a" * 64,
        dedup_status="new",
        kb_status="pending",
        graph_status="pending",
        request_schema_version="1.0",
    )
    db_session.add_all([version, job])
    await db_session.flush()
    return paper, version, job

