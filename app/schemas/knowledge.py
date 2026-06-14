from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeDocumentIn(BaseModel):
    document_key: str = Field(..., min_length=1, examples=["arxiv:2406.09246:profile"])
    name: str = Field(..., min_length=1, examples=["Paper Title - Paper Profile"])
    content: str = Field(..., min_length=1, examples=["# Paper Profile\n..."])
    metadata: dict[str, Any] = Field(default_factory=dict)


class KbDocumentRead(BaseModel):
    document_key: str
    content_hash: str
    provider: str
    dataset_id: str | None = None
    remote_document_id: str | None = None
    batch_id: str | None = None
    indexing_status: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class ExternalRetrievalRequest(BaseModel):
    query: str = Field(..., min_length=1)
    paper_id: str | None = None
    top_k: int = Field(default=5, ge=1, le=50)


class ExternalRetrievalResponse(BaseModel):
    results: list[dict[str, Any]] = Field(default_factory=list)

