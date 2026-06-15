from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "paper-ingestion-service"
    app_env: str = "local"
    log_level: str = "INFO"
    enable_public_docs: bool = True
    max_request_bytes: int = 2_000_000

    database_url: str = "postgresql+psycopg://postgres:postgres@postgres:5432/papers"
    redis_url: str = "redis://redis:6379/0"
    queue_mode: Literal["inline", "celery"] = "inline"
    max_retry_count: int = 3

    app_api_keys: str = "dev-secret-change-me"
    app_admin_api_keys: str = ""

    enable_dify_sync: bool = False
    dify_api_base_url: str = "https://api.dify.ai/v1"
    dify_kb_api_key: str | None = None
    dify_papers_dataset_id: str | None = None
    dify_indexing_technique: str = "high_quality"
    dify_poll_interval_seconds: float = 1.0
    dify_index_timeout_seconds: float = 120.0
    provider_connect_timeout_seconds: float = 5.0
    provider_read_timeout_seconds: float = 30.0

    enable_neo4j_sync: bool = False
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str | None = None
    neo4j_database: str = "neo4j"

    enable_object_storage: bool = False
    s3_endpoint_url: str | None = None
    s3_region: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_public_base_url: str | None = None

    enable_external_retrieval_api: bool = False

    enable_workflow_gateway: bool = True
    dify_workflow_api_base_url: str = "https://api.dify.ai/v1"
    dify_workflow_api_key: str | None = None
    workflow_gateway_queue: str = "workflow_gateway"
    workflow_gateway_max_runtime_seconds: int = 1800
    workflow_gateway_connect_timeout_seconds: float = 30.0
    workflow_gateway_sse_read_timeout_seconds: float = 1800.0
    workflow_gateway_reconnect_max_attempts: int = 10
    workflow_gateway_reconnect_base_delay_seconds: float = 3.0
    workflow_gateway_upload_dir: str = "/var/lib/paper-service/workflow-gateway"
    workflow_gateway_max_upload_mb: int = 50
    workflow_gateway_result_retention_days: int = 30
    workflow_gateway_max_concurrent_jobs_per_owner: int = 3
    workflow_gateway_store_events: bool = False
    workflow_gateway_auto_ingest: bool = False
    workflow_gateway_worker_concurrency: int = 2

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def api_keys(self) -> list[str]:
        return [item.strip() for item in self.app_api_keys.split(",") if item.strip()]

    @property
    def admin_api_keys(self) -> list[str]:
        return [item.strip() for item in self.app_admin_api_keys.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
