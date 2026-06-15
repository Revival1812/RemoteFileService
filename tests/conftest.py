import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("APP_API_KEYS", "test-key")
os.environ.setdefault("APP_ADMIN_API_KEYS", "admin-key")
os.environ.setdefault("QUEUE_MODE", "inline")
os.environ.setdefault("ENABLE_DIFY_SYNC", "false")
os.environ.setdefault("ENABLE_NEO4J_SYNC", "false")
os.environ.setdefault("ENABLE_WORKFLOW_GATEWAY", "true")
os.environ.setdefault("DIFY_WORKFLOW_API_KEY", "")
os.environ.setdefault("WORKFLOW_GATEWAY_UPLOAD_DIR", "./test_uploads")

from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture(autouse=True)
async def reset_db() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


def auth(key: str = "test-key") -> dict[str, str]:
    return {"Authorization": f"Bearer {key}", "X-Owner-Id": "owner-1"}


def payload(
    *,
    paper_id: str = "arxiv:2406.09246",
    content_hash: str = "a" * 64,
    document_key: str = "arxiv:2406.09246:profile",
    title: str = "A Practical Paper",
) -> dict:
    return {
        "schema_version": "1.0",
        "paper_id": paper_id,
        "content_hash": content_hash,
        "profile": {"title": title, "year": 2024, "authors": ["Ada"]},
        "knowledge_documents": [
            {
                "document_key": document_key,
                "name": f"{title} - Paper Profile",
                "content": "# Profile\nShort content",
                "metadata": {
                    "paper_id": paper_id,
                    "content_hash": content_hash,
                    "content_type": "paper_profile",
                },
            }
        ],
        "graph": {
            "paper_id": paper_id,
            "nodes": [
                {"uid": "entity:a", "name": "A", "type": "Method"},
                {"uid": "entity:b", "name": "B", "type": "Dataset"},
            ],
            "edges": [
                {
                    "source_uid": "entity:a",
                    "target_uid": "entity:b",
                    "relation": "USES",
                    "evidence": "A uses B.",
                    "confidence": 0.9,
                }
            ],
        },
        "source_metadata": {
            "source_type": "upload",
            "arxiv_id": "2406.09246",
            "doi": "",
            "owner_id": "owner-1",
            "access_scope": "private",
        },
    }
