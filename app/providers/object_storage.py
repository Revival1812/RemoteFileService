from typing import Any

from app.core.config import Settings
from app.providers.base import ProviderResult, elapsed_timer


class ObjectStorageProviderImpl:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def sync_artifacts(self, *, session: Any, paper: Any, version: Any, job: Any) -> ProviderResult:
        with elapsed_timer() as timer:
            return ProviderResult(
                provider="object_storage",
                status="skipped",
                message="artifact upload adapter reserved",
                elapsed_ms=timer.elapsed_ms,
            )

