from typing import Any

from app.providers.base import ProviderResult


class DisabledKnowledgeProvider:
    async def sync_documents(self, *, session: Any, paper: Any, version: Any, job: Any) -> ProviderResult:
        return ProviderResult.disabled("dify")


class DisabledGraphProvider:
    async def sync_graph(self, *, session: Any, paper: Any, version: Any, job: Any) -> ProviderResult:
        return ProviderResult.disabled("neo4j")


class DisabledObjectStorageProvider:
    async def sync_artifacts(self, *, session: Any, paper: Any, version: Any, job: Any) -> ProviderResult:
        return ProviderResult.disabled("object_storage")


class DisabledExternalKnowledgeRetriever:
    async def retrieve(self, query: str, *, top_k: int = 5, paper_id: str | None = None) -> list[dict[str, Any]]:
        return []

