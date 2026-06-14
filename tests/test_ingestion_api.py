import asyncio

from sqlalchemy import func, select

from app.models.paper_version import PaperVersion
from tests.conftest import auth, payload


async def test_new_paper_registration(client):
    response = await client.post("/v1/ingestion/jobs", json=payload(), headers=auth())
    assert response.status_code == 202
    body = response.json()
    assert body["dedup_status"] == "new"
    assert body["paper_id"] == "arxiv:2406.09246"


async def test_exact_duplicate_paper(client, db_session):
    first = await client.post("/v1/ingestion/jobs", json=payload(), headers=auth())
    second = await client.post("/v1/ingestion/jobs", json=payload(), headers=auth())
    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["dedup_status"] == "existing"
    version_count = await db_session.scalar(select(func.count()).select_from(PaperVersion))
    assert version_count == 1


async def test_same_paper_new_content_hash(client, db_session):
    await client.post("/v1/ingestion/jobs", json=payload(), headers=auth())
    updated = payload(content_hash="b" * 64)
    updated["source_metadata"]["arxiv_id"] = "2406.09246"
    response = await client.post("/v1/ingestion/jobs", json=updated, headers=auth())
    assert response.status_code == 202
    assert response.json()["dedup_status"] == "new_version"
    version_count = await db_session.scalar(select(func.count()).select_from(PaperVersion))
    assert version_count == 2


async def test_concurrent_submit_same_paper(client, db_session):
    body = payload(paper_id="arxiv:concurrent", document_key="arxiv:concurrent:profile")
    body["source_metadata"]["arxiv_id"] = "concurrent"
    responses = await asyncio.gather(
        client.post("/v1/ingestion/jobs", json=body, headers=auth()),
        client.post("/v1/ingestion/jobs", json=body, headers=auth()),
    )
    assert all(response.status_code == 202 for response in responses)
    version_count = await db_session.scalar(select(func.count()).select_from(PaperVersion))
    assert version_count == 1


async def test_document_key_duplicate(client):
    body = payload()
    body["knowledge_documents"].append(body["knowledge_documents"][0].copy())
    response = await client.post("/v1/ingestion/jobs", json=body, headers=auth())
    assert response.status_code == 422


async def test_invalid_content_hash(client):
    response = await client.post("/v1/ingestion/jobs", json=payload(content_hash="not-sha"), headers=auth())
    assert response.status_code == 422


async def test_graph_dangling_edge(client):
    body = payload()
    body["graph"]["edges"][0]["target_uid"] = "missing"
    response = await client.post("/v1/ingestion/jobs", json=body, headers=auth())
    assert response.status_code == 422


async def test_graph_duplicate_nodes(client):
    body = payload()
    body["graph"]["nodes"].append(body["graph"]["nodes"][0].copy())
    response = await client.post("/v1/ingestion/jobs", json=body, headers=auth())
    assert response.status_code == 422


async def test_api_key_missing(client):
    response = await client.post("/v1/ingestion/jobs", json=payload())
    assert response.status_code == 401


async def test_api_key_wrong(client):
    response = await client.post("/v1/ingestion/jobs", json=payload(), headers=auth("wrong"))
    assert response.status_code == 401


async def test_query_job(client):
    created = await client.post("/v1/ingestion/jobs", json=payload(), headers=auth())
    job_id = created.json()["job_id"]
    response = await client.get(f"/v1/ingestion/jobs/{job_id}", headers=auth())
    assert response.status_code == 200
    assert response.json()["job_id"] == job_id


async def test_query_paper_and_versions(client):
    await client.post("/v1/ingestion/jobs", json=payload(), headers=auth())
    paper = await client.get("/v1/papers/arxiv:2406.09246", headers=auth())
    versions = await client.get("/v1/papers/arxiv:2406.09246/versions", headers=auth())
    assert paper.status_code == 200
    assert paper.json()["latest_version"] == 1
    assert versions.status_code == 200
    assert len(versions.json()) == 1

