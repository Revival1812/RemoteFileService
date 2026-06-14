import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.graph import ALLOWED_RELATIONS, GraphPayload
from app.schemas.knowledge import KnowledgeDocumentIn

SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class SourceMetadata(BaseModel):
    source_type: str | None = None
    arxiv_id: str | None = None
    doi: str | None = None
    owner_id: str | None = None
    access_scope: Literal["private", "shared", "public"] = "private"


class IngestionJobCreate(BaseModel):
    schema_version: str = Field(..., examples=["1.0"])
    paper_id: str = Field(..., min_length=1, examples=["arxiv:2406.09246"])
    content_hash: str = Field(..., examples=["0" * 64])
    profile: dict[str, Any] = Field(default_factory=dict)
    knowledge_documents: list[KnowledgeDocumentIn] = Field(default_factory=list)
    graph: GraphPayload | None = None
    source_metadata: SourceMetadata = Field(default_factory=SourceMetadata)

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "schema_version": "1.0",
                    "paper_id": "arxiv:2406.09246",
                    "content_hash": "0" * 64,
                    "profile": {"title": "Example Paper", "year": 2024},
                    "knowledge_documents": [
                        {
                            "document_key": "arxiv:2406.09246:profile",
                            "name": "Example Paper - Paper Profile",
                            "content": "# Example Paper",
                            "metadata": {
                                "paper_id": "arxiv:2406.09246",
                                "content_hash": "0" * 64,
                                "content_type": "paper_profile",
                            },
                        }
                    ],
                    "graph": {"paper_id": "arxiv:2406.09246", "nodes": [], "edges": []},
                    "source_metadata": {
                        "source_type": "upload",
                        "arxiv_id": "",
                        "doi": "",
                        "owner_id": "user-1",
                        "access_scope": "private",
                    },
                }
            ]
        }
    )

    @model_validator(mode="after")
    def validate_payload(self) -> "IngestionJobCreate":
        if not SHA256_RE.fullmatch(self.content_hash):
            raise ValueError("content_hash must be a 64 character hexadecimal SHA-256")
        document_keys = [doc.document_key for doc in self.knowledge_documents]
        if len(document_keys) != len(set(document_keys)):
            raise ValueError("knowledge_documents document_key values must be unique")
        if self.graph is not None:
            if self.graph.paper_id != self.paper_id:
                raise ValueError("graph.paper_id must match paper_id")
            node_uids = [node.uid for node in self.graph.nodes]
            if len(node_uids) != len(set(node_uids)):
                raise ValueError("graph nodes must have unique uid values")
            node_set = set(node_uids)
            for edge in self.graph.edges:
                if edge.source_uid not in node_set or edge.target_uid not in node_set:
                    raise ValueError("graph edge source_uid and target_uid must exist in nodes")
                if edge.source_uid == edge.target_uid:
                    raise ValueError("graph self loops are not allowed")
                if edge.relation not in ALLOWED_RELATIONS:
                    raise ValueError(f"graph edge relation must be one of {sorted(ALLOWED_RELATIONS)}")
        return self


class IngestionAcceptedResponse(BaseModel):
    accepted: bool = True
    job_id: str
    paper_id: str
    dedup_status: Literal["new", "existing", "new_version", "possible_duplicate"]
    kb_status: Literal["pending", "skipped", "disabled", "completed", "failed"]
    graph_status: Literal["pending", "skipped", "disabled", "completed", "failed"]
    warnings: list[str] = Field(default_factory=list)


class RetryJobResponse(BaseModel):
    accepted: bool = True
    job_id: str

