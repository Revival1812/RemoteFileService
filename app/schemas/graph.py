
from pydantic import BaseModel, ConfigDict, Field

ALLOWED_RELATIONS = {
    "USES",
    "IMPROVES",
    "COMPARES_WITH",
    "EVALUATES_ON",
    "PROPOSES",
    "MENTIONS",
    "RELATES_TO",
    "PART_OF",
    "CAUSES",
}


class GraphNode(BaseModel):
    uid: str = Field(..., min_length=1, examples=["entity:transformer"])
    name: str = Field(..., min_length=1, examples=["Transformer"])
    type: str = Field(..., min_length=1, examples=["Method"])
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None


class GraphEdge(BaseModel):
    source_uid: str = Field(..., min_length=1)
    target_uid: str = Field(..., min_length=1)
    relation: str = Field(..., min_length=1, examples=["USES"])
    evidence: str = Field(..., min_length=1)
    section: str | None = None
    page: int | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class GraphPayload(BaseModel):
    paper_id: str
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)

    model_config = ConfigDict(json_schema_extra={"examples": [{"paper_id": "arxiv:2406.09246", "nodes": [], "edges": []}]})


class GraphSyncRequest(BaseModel):
    content_hash: str | None = None


class GraphSyncRecordRead(BaseModel):
    id: str
    paper_id: str
    content_hash: str
    node_count: int
    edge_count: int
    sync_status: str
    error_message: str | None = None

