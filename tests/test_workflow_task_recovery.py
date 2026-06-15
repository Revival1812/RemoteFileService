

from app.core.config import Settings
from app.models.workflow_job import WorkflowJob
from app.services.workflow_gateway_service import WorkflowJobRunner


async def seed_workflow_job(db_session, **overrides) -> WorkflowJob:
    values = {
        "job_id": overrides.pop("job_id", "wjob_seed"),
        "source_type": overrides.pop("source_type", "arxiv"),
        "status": overrides.pop("status", "queued"),
        "owner_id": overrides.pop("owner_id", "owner-1"),
        "access_scope": overrides.pop("access_scope", "private"),
        "dify_user": overrides.pop("dify_user", "owner-1"),
        "request_inputs_json": overrides.pop(
            "request_inputs_json",
            {
                "source_type": "arxiv",
                "paper_file": None,
                "supplementary_images": [],
                "arxiv_id": "2602.11929",
                "owner_id": "owner-1",
                "access_scope": "private",
            },
        ),
        "temporary_file_manifest_json": overrides.pop("temporary_file_manifest_json", []),
    }
    values.update(overrides)
    job = WorkflowJob(**values)
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


async def test_sse_workflow_started(db_session):
    job = await seed_workflow_job(db_session)
    runner = WorkflowJobRunner(db_session, Settings())
    await runner.apply_event(job, {"event": "workflow_started", "task_id": "task-1", "workflow_run_id": "run-1"})
    assert job.status == "running"
    assert job.dify_task_id == "task-1"
    assert job.dify_workflow_run_id == "run-1"


async def test_sse_node_started_and_retry(db_session):
    job = await seed_workflow_job(db_session)
    runner = WorkflowJobRunner(db_session, Settings())
    await runner.apply_event(job, {"event": "node_started", "data": {"node_id": "n1", "title": "Node 1"}})
    await runner.apply_event(job, {"event": "node_retry", "data": {"node_id": "n1", "title": "Node 1"}})
    assert job.current_node_id == "n1"
    assert job.current_node_title == "Node 1"
    assert job.event_count == 2


async def test_sse_finished_succeeded_and_cleanup(db_session, tmp_path):
    temp_file = tmp_path / "paper.pdf"
    temp_file.write_bytes(b"%PDF-1.4")
    job = await seed_workflow_job(
        db_session,
        temporary_file_manifest_json=[{"path": str(temp_file), "kind": "paper_file"}],
    )
    runner = WorkflowJobRunner(db_session, Settings(workflow_gateway_upload_dir=str(tmp_path)))
    await runner.apply_event(
        job,
        {
            "event": "workflow_finished",
            "data": {
                "status": "succeeded",
                "outputs": {"paper_result": {"title": "Paper", "summary": "Done"}},
            },
        },
    )
    assert job.status == "succeeded"
    assert job.result_summary_json["title"] == "Paper"
    assert not temp_file.exists()


async def test_sse_finished_failed(db_session):
    job = await seed_workflow_job(db_session)
    runner = WorkflowJobRunner(db_session, Settings())
    await runner.apply_event(
        job,
        {"event": "workflow_finished", "data": {"status": "failed", "error": "bad"}},
    )
    assert job.status == "failed"
    assert job.error_message == "bad"


async def test_recover_from_run_detail_success(httpx_mock, db_session):
    job = await seed_workflow_job(db_session, status="running", dify_workflow_run_id="run-1")
    settings = Settings(dify_workflow_api_base_url="https://dify.test/v1", dify_workflow_api_key="secret")
    httpx_mock.add_response(
        method="GET",
        url="https://dify.test/v1/workflows/run/run-1",
        json={"status": "succeeded", "outputs": {"paper_result": {"title": "Recovered"}}},
    )
    await WorkflowJobRunner(db_session, settings).run(job.job_id)
    await db_session.refresh(job)
    assert job.status == "succeeded"
    assert job.result_summary_json["title"] == "Recovered"
    assert not any(request.method == "POST" and "/workflows/run" in str(request.url) for request in httpx_mock.get_requests())


async def test_recover_events_after_disconnect(httpx_mock, db_session):
    job = await seed_workflow_job(db_session, status="running", dify_task_id="task-1", dify_workflow_run_id="run-1")
    settings = Settings(dify_workflow_api_base_url="https://dify.test/v1", dify_workflow_api_key="secret")
    httpx_mock.add_response(
        method="GET",
        url="https://dify.test/v1/workflow/task-1/events?user=owner-1&include_state_snapshot=true",
        json=[
            {"event": "workflow_finished", "data": {"status": "succeeded", "outputs": {"paper_result": {"title": "Recovered"}}}}
        ],
    )
    await WorkflowJobRunner(db_session, settings).run(job.job_id)
    await db_session.refresh(job)
    assert job.status == "succeeded"


async def test_recover_unfinished_jobs(db_session, httpx_mock):
    job = await seed_workflow_job(db_session, status="running", dify_workflow_run_id="run-1")
    settings = Settings(dify_workflow_api_base_url="https://dify.test/v1", dify_workflow_api_key="secret")
    httpx_mock.add_response(
        method="GET",
        url="https://dify.test/v1/workflows/run/run-1",
        json={"status": "succeeded", "outputs": {"paper_result": {"title": "Recovered"}}},
    )
    count = await WorkflowJobRunner(db_session, settings).recover_unfinished()
    await db_session.refresh(job)
    assert count == 1
    assert job.status == "succeeded"


async def test_cancel_running_job_calls_dify_stop(client, db_session, httpx_mock):
    job = await seed_workflow_job(db_session, status="running", dify_task_id="task-1")
    app_settings = Settings(dify_workflow_api_base_url="https://dify.test/v1", dify_workflow_api_key="secret")
    from app.core.config import get_settings
    from app.main import app
    from tests.conftest import auth

    app.dependency_overrides[get_settings] = lambda: app_settings
    httpx_mock.add_response(method="POST", url="https://dify.test/v1/workflows/tasks/task-1/stop", json={"result": "ok"})
    try:
        response = await client.post(f"/v1/workflow-jobs/{job.job_id}/cancel", headers=auth())
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

