
from app.core.config import Settings
from app.providers.dify_workflow import DifyWorkflowProvider


def test_parse_sse_ignores_ping_blank_and_done():
    assert DifyWorkflowProvider.parse_sse_line("") is None
    assert DifyWorkflowProvider.parse_sse_line("ping") is None
    assert DifyWorkflowProvider.parse_sse_line("data: [DONE]") is None


def test_parse_sse_json_event():
    event = DifyWorkflowProvider.parse_sse_line('data: {"event":"node_started","data":{"node_id":"n1"}}')
    assert event["event"] == "node_started"


async def test_upload_and_workflow_use_same_user(httpx_mock, tmp_path):
    file_path = tmp_path / "paper.pdf"
    file_path.write_bytes(b"%PDF-1.4\ncontent")
    settings = Settings(
        dify_workflow_api_base_url="https://dify.test/v1",
        dify_workflow_api_key="secret",
    )
    httpx_mock.add_response(method="POST", url="https://dify.test/v1/files/upload", json={"id": "file-1"})
    httpx_mock.add_response(
        method="POST",
        url="https://dify.test/v1/workflows/run",
        content=(
            b'data: {"event":"workflow_started","task_id":"task-1","workflow_run_id":"run-1"}\n\n'
            b'data: {"event":"workflow_finished","data":{"status":"succeeded","outputs":{"paper_result":{"title":"T"}}}}\n\n'
        ),
        headers={"content-type": "text/event-stream"},
    )
    provider = DifyWorkflowProvider(settings)
    try:
        upload_id = await provider.upload_file(
            path=file_path,
            user="owner-1",
            file_type="document",
            mime_type="application/pdf",
        )
        events = [event async for event in provider.run_workflow(inputs={"paper_file": upload_id}, user="owner-1")]
    finally:
        await provider.close()
    assert upload_id == "file-1"
    assert events[-1]["event"] == "workflow_finished"
    upload_request, run_request = httpx_mock.get_requests()
    assert b'name="user"\r\n\r\nowner-1' in upload_request.content
    assert b'"user":"owner-1"' in run_request.content

