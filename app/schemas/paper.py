from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class PaperRead(BaseModel):
    id: str
    paper_id: str
    canonical_title: str | None = None
    normalized_title: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    authors_json: dict[str, Any] | None = None
    year: int | None = None
    latest_content_hash: str | None = None
    latest_version: int
    status: str
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaperListResponse(BaseModel):
    items: list[PaperRead]
    limit: int
    offset: int


class PaperVersionRead(BaseModel):
    id: str
    paper_id: str
    version_number: int
    content_hash: str
    profile_json: dict[str, Any]
    graph_json: dict[str, Any] | None = None
    source_metadata_json: dict[str, Any]
    knowledge_documents_json: list[dict[str, Any]]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DuplicateCandidateRead(BaseModel):
    id: str
    paper_id_a: str
    paper_id_b: str
    similarity_score: float
    reason: str
    review_status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DuplicateCandidateUpdate(BaseModel):
    review_status: Literal["pending", "confirmed", "rejected", "merged"]

