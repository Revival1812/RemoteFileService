import time
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ProviderResult:
    provider: str
    status: str
    message: str | None = None
    remote_id: str | None = None
    batch_id: str | None = None
    elapsed_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def disabled(cls, provider: str) -> "ProviderResult":
        return cls(provider=provider, status="disabled", message="provider disabled")


class KnowledgeProvider(Protocol):
    async def sync_documents(self, *, session: Any, paper: Any, version: Any, job: Any) -> ProviderResult:
        ...


class GraphProvider(Protocol):
    async def sync_graph(self, *, session: Any, paper: Any, version: Any, job: Any) -> ProviderResult:
        ...


class ObjectStorageProvider(Protocol):
    async def sync_artifacts(self, *, session: Any, paper: Any, version: Any, job: Any) -> ProviderResult:
        ...


class ExternalKnowledgeRetriever(Protocol):
    async def retrieve(self, query: str, *, top_k: int = 5, paper_id: str | None = None) -> list[dict[str, Any]]:
        ...


class elapsed_timer:
    def __enter__(self) -> "elapsed_timer":
        self.started = time.monotonic()
        self.elapsed_ms = 0
        return self

    def __exit__(self, *_: object) -> None:
        self.elapsed_ms = int((time.monotonic() - self.started) * 1000)

