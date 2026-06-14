import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
job_id_ctx: ContextVar[str | None] = ContextVar("job_id", default=None)
paper_id_ctx: ContextVar[str | None] = ContextVar("paper_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if request_id := request_id_ctx.get():
            payload["request_id"] = request_id
        if job_id := job_id_ctx.get():
            payload["job_id"] = job_id
        if paper_id := paper_id_ctx.get():
            payload["paper_id"] = paper_id
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())


def bind_request_context(
    *, request_id: str | None = None, job_id: str | None = None, paper_id: str | None = None
) -> None:
    if request_id is not None:
        request_id_ctx.set(request_id)
    if job_id is not None:
        job_id_ctx.set(job_id)
    if paper_id is not None:
        paper_id_ctx.set(paper_id)

