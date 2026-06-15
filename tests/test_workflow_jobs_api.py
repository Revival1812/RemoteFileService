
from app.core.config import Settings, get_settings
from app.main import app
from app.models.workflow_job import WorkflowJob
from tests.conftest import auth, payload


def arxiv_payload(owner_id: str = "owner-1") -> dict:
    return {
        "source_type": "arxiv",
        "arxiv_id": "2602.11929",
        "analysis_id": "analysis-1",
        "action": "analyze_arxiv",
        "user_query": "请完整解析这篇论文",
        "user_level": "研究生或研究人员",
        "force_accept": False,
        "allow_ingestion": False,
        "parser_mode": "auto",
        "analysis_depth": "full",
        "owner_id": owner_id,
        "access_scope": "private",
    }


async def test_gateway_disabled_but_old_health_and_ingestion_work(client):
    app.dependency_overrides[get_settings] = lambda: Settings(enable_workflow_gateway=False)
    try:
        disabled = await client.post("/v1/workflow-jobs/arxiv", json=arxiv_payload(), headers=auth())
        health = await client.get("/healthz")
        old = await client.post("/v1/ingestion/jobs", json=payload(), headers=auth())
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert disabled.status_code == 404
    assert health.status_code == 200
    assert old.status_code == 202


async def test_workflow_requires_api_key(client):
    response = await client.post("/v1/workflow-jobs/arxiv", json=arxiv_payload())
    assert response.status_code == 401


async def test_arxiv_submit_returns_202(client):
    response = await client.post("/v1/workflow-jobs/arxiv", json=arxiv_payload(), headers=auth())
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["status_url"].startswith("/v1/workflow-jobs/wjob_")


async def test_idempotency_key_returns_existing_job(client, db_session):
    headers = {**auth(), "Idempotency-Key": "idem-1"}
    first = await client.post("/v1/workflow-jobs/arxiv", json=arxiv_payload(), headers=headers)
    second = await client.post("/v1/workflow-jobs/arxiv", json=arxiv_payload(), headers=headers)
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]


async def test_private_owner_permission(client):
    created = await client.post("/v1/workflow-jobs/arxiv", json=arxiv_payload(), headers=auth())
    job_id = created.json()["job_id"]
    denied = await client.get(f"/v1/workflow-jobs/{job_id}", headers=auth() | {"X-Owner-Id": "other"})
    allowed = await client.get(f"/v1/workflow-jobs/{job_id}", headers=auth())
    assert denied.status_code == 403
    assert allowed.status_code == 200


async def test_admin_can_read_private_job(client):
    created = await client.post("/v1/workflow-jobs/arxiv", json=arxiv_payload(), headers=auth())
    job_id = created.json()["job_id"]
    response = await client.get(f"/v1/workflow-jobs/{job_id}", headers=auth("admin-key"))
    assert response.status_code == 200


async def test_upload_submit_returns_202_and_supplementary_images_empty(client, db_session):
    files = {"paper_file": ("paper.pdf", b"%PDF-1.4\ncontent", "application/pdf")}
    data = {
        "owner_id": "owner-1",
        "analysis_id": "upload-1",
        "action": "analyze_upload",
        "user_query": "解析上传论文",
        "user_level": "研究生或研究人员",
        "parser_mode": "auto",
        "analysis_depth": "full",
        "access_scope": "private",
    }
    response = await client.post("/v1/workflow-jobs/upload", data=data, files=files, headers=auth())
    assert response.status_code == 202
    job = await db_session.get(WorkflowJob, (await _job_uuid(db_session, response.json()["job_id"])))
    assert job.request_inputs_json["supplementary_images"] == []
    assert len(job.temporary_file_manifest_json) == 1


async def test_upload_rejects_multiple_paper_files(client):
    files = [
        ("paper_file", ("a.pdf", b"%PDF-1.4\ncontent", "application/pdf")),
        ("paper_file", ("b.pdf", b"%PDF-1.4\ncontent", "application/pdf")),
    ]
    response = await client.post("/v1/workflow-jobs/upload", data={"owner_id": "owner-1"}, files=files, headers=auth())
    assert response.status_code == 422


async def test_upload_rejects_size_limit(client):
    app.dependency_overrides[get_settings] = lambda: Settings(
        enable_workflow_gateway=True,
        workflow_gateway_max_upload_mb=0,
        workflow_gateway_upload_dir="./test_uploads",
    )
    try:
        response = await client.post(
            "/v1/workflow-jobs/upload",
            data={"owner_id": "owner-1"},
            files={"paper_file": ("paper.pdf", b"%PDF-1.4\ncontent", "application/pdf")},
            headers=auth(),
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert response.status_code == 413


async def test_upload_rejects_mime_or_extension(client):
    response = await client.post(
        "/v1/workflow-jobs/upload",
        data={"owner_id": "owner-1"},
        files={"paper_file": ("paper.exe", b"MZ", "application/octet-stream")},
        headers=auth(),
    )
    assert response.status_code == 422


async def test_result_summary_and_full_views(client, db_session):
    created = await client.post("/v1/workflow-jobs/arxiv", json=arxiv_payload(), headers=auth())
    job_id = created.json()["job_id"]
    job = await _job_by_public_id(db_session, job_id)
    job.status = "succeeded"
    job.result_summary_json = {"title": "Short"}
    job.result_json = {"paper_result": {"title": "Full", "body": "details"}}
    await db_session.commit()
    summary = await client.get(f"/v1/workflow-jobs/{job_id}/result?view=summary", headers=auth())
    full = await client.get(f"/v1/workflow-jobs/{job_id}/result?view=full", headers=auth())
    assert summary.json()["result"] == {"title": "Short"}
    assert full.json()["result"]["paper_result"]["title"] == "Full"


async def test_queued_result_returns_202(client):
    created = await client.post("/v1/workflow-jobs/arxiv", json=arxiv_payload(), headers=auth())
    response = await client.get(f"/v1/workflow-jobs/{created.json()['job_id']}/result", headers=auth())
    assert response.status_code == 202


async def test_cancel_queued_job(client):
    created = await client.post("/v1/workflow-jobs/arxiv", json=arxiv_payload(), headers=auth())
    response = await client.post(f"/v1/workflow-jobs/{created.json()['job_id']}/cancel", headers=auth())
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


async def test_admin_workflow_gateway_status(client):
    response = await client.get("/v1/admin/workflow-gateway/status", headers=auth("admin-key"))
    assert response.status_code == 200
    assert response.json()["queue_name"] == "workflow_gateway"


async def _job_by_public_id(db_session, job_id: str) -> WorkflowJob:
    from sqlalchemy import select

    return await db_session.scalar(select(WorkflowJob).where(WorkflowJob.job_id == job_id))


async def _job_uuid(db_session, job_id: str):
    job = await _job_by_public_id(db_session, job_id)
    return job.id
