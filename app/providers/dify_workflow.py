import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


class DifyWorkflowProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        timeout = httpx.Timeout(
            connect=settings.workflow_gateway_connect_timeout_seconds,
            read=settings.workflow_gateway_sse_read_timeout_seconds,
            write=settings.workflow_gateway_connect_timeout_seconds,
            pool=settings.workflow_gateway_connect_timeout_seconds,
        )
        self.client = httpx.AsyncClient(
            base_url=settings.dify_workflow_api_base_url.rstrip("/"),
            timeout=timeout,
            headers={"Authorization": f"Bearer {settings.dify_workflow_api_key or ''}"},
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def upload_file(self, *, path: Path, user: str, file_type: str, mime_type: str) -> str:
        with path.open("rb") as handle:
            files = {"file": (path.name, handle, mime_type)}
            response = await self.client.post("/files/upload", data={"user": user}, files=files)
        response.raise_for_status()
        body = response.json()
        upload_id = body.get("id") or body.get("data", {}).get("id")
        if not upload_id:
            raise RuntimeError("Dify file upload response did not include id")
        return str(upload_id)

    async def run_workflow(self, *, inputs: dict[str, Any], user: str) -> AsyncIterator[dict[str, Any]]:
        payload = {"inputs": inputs, "response_mode": "streaming", "user": user}
        headers = {
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
        }
        async with self.client.stream("POST", "/workflows/run", json=payload, headers=headers) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                event = self.parse_sse_line(line)
                if event is not None:
                    yield event

    async def recover_events(self, *, task_id: str, user: str) -> list[dict[str, Any]]:
        response = await self.client.get(
            f"/workflow/{task_id}/events",
            params={"user": user, "include_state_snapshot": "true"},
        )
        response.raise_for_status()
        body = response.json()
        if isinstance(body, list):
            return body
        data = body.get("data", body)
        return data if isinstance(data, list) else [data]

    async def get_run_detail(self, *, workflow_run_id: str) -> dict[str, Any]:
        response = await self.client.get(f"/workflows/run/{workflow_run_id}")
        response.raise_for_status()
        return response.json()

    async def stop_task(self, *, task_id: str, user: str) -> dict[str, Any]:
        response = await self.client.post(f"/workflows/tasks/{task_id}/stop", json={"user": user})
        response.raise_for_status()
        return response.json()

    @staticmethod
    def parse_sse_line(line: str) -> dict[str, Any] | None:
        stripped = line.strip()
        if not stripped or stripped == "ping" or stripped == "[DONE]":
            return None
        if stripped.startswith(":"):
            return None
        if stripped.startswith("data:"):
            stripped = stripped[5:].strip()
        if not stripped or stripped == "[DONE]" or stripped == "ping":
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            logger.debug("Ignoring non-json SSE line from Dify workflow")
            return None
