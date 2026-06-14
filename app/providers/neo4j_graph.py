import logging
from typing import Any

from neo4j import AsyncGraphDatabase

from app.core.config import Settings
from app.providers.base import ProviderResult, elapsed_timer
from app.schemas.graph import ALLOWED_RELATIONS

logger = logging.getLogger(__name__)


class Neo4jGraphProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password or ""),
        )

    async def close(self) -> None:
        await self.driver.close()

    async def initialize(self) -> None:
        async with self.driver.session(database=self.settings.neo4j_database) as session:
            await session.run(
                "CREATE CONSTRAINT entity_uid IF NOT EXISTS FOR (n:Entity) REQUIRE n.uid IS UNIQUE"
            )
            try:
                await session.run(
                    "CREATE CONSTRAINT relates_to_edge_key IF NOT EXISTS "
                    "FOR ()-[r:RELATES_TO]-() REQUIRE r.edge_key IS UNIQUE"
                )
            except Exception:
                logger.info("Neo4j relationship uniqueness constraint not supported by this version")

    async def sync_graph(self, *, session: Any, paper: Any, version: Any, job: Any) -> ProviderResult:
        graph = version.graph_json or {}
        nodes = graph.get("nodes") or []
        edges = graph.get("edges") or []
        if not nodes and not edges:
            return ProviderResult(provider="neo4j", status="skipped", message="empty graph")
        with elapsed_timer() as timer:
            try:
                self._validate_graph(nodes, edges, paper.paper_id)
                prepared_edges = [
                    {**edge, "paper_id": paper.paper_id, "edge_key": self.edge_key(edge, paper.paper_id)}
                    for edge in edges
                ]
                await self.initialize()
                async with self.driver.session(database=self.settings.neo4j_database) as neo_session:
                    await neo_session.execute_write(self._upsert_graph, nodes, prepared_edges)
                return ProviderResult(
                    provider="neo4j",
                    status="completed",
                    message="graph synced",
                    elapsed_ms=timer.elapsed_ms,
                    metadata={"node_count": len(nodes), "edge_count": len(edges)},
                )
            except Exception as exc:
                logger.exception("Neo4j sync failed", extra={"extra_fields": {"provider": "neo4j"}})
                return ProviderResult(provider="neo4j", status="failed", message=str(exc), elapsed_ms=timer.elapsed_ms)

    @staticmethod
    def edge_key(edge: dict[str, Any], paper_id: str) -> str:
        return f"{edge['source_uid']}|{edge['relation']}|{edge['target_uid']}|{paper_id}"

    @staticmethod
    async def _upsert_graph(tx: Any, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
        await tx.run(
            """
            UNWIND $nodes AS n
            MERGE (entity:Entity {uid: n.uid})
            ON CREATE SET entity.created_at = datetime()
            SET entity.name = n.name,
                entity.type = n.type,
                entity.aliases = coalesce(n.aliases, []),
                entity.description = n.description,
                entity.updated_at = datetime()
            """,
            nodes=nodes,
        )
        await tx.run(
            """
            UNWIND $edges AS e
            MATCH (source:Entity {uid: e.source_uid})
            MATCH (target:Entity {uid: e.target_uid})
            MERGE (source)-[r:RELATES_TO {edge_key: e.edge_key}]->(target)
            SET r.relation = e.relation,
                r.paper_id = e.paper_id,
                r.evidence = e.evidence,
                r.section = e.section,
                r.page = e.page,
                r.confidence = e.confidence,
                r.updated_at = datetime()
            """,
            edges=edges,
        )

    @staticmethod
    def _validate_graph(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], paper_id: str) -> None:
        uids = [node["uid"] for node in nodes]
        if len(uids) != len(set(uids)):
            raise ValueError("duplicate graph node uid")
        uid_set = set(uids)
        for edge in edges:
            if edge["source_uid"] not in uid_set or edge["target_uid"] not in uid_set:
                raise ValueError("dangling graph edge")
            if edge["source_uid"] == edge["target_uid"]:
                raise ValueError("self loop is not allowed")
            if edge["relation"] not in ALLOWED_RELATIONS:
                raise ValueError("relation is not allowed")
            if not edge.get("evidence"):
                raise ValueError("edge evidence is required")
            confidence = edge.get("confidence", 1.0)
            if confidence < 0 or confidence > 1:
                raise ValueError("edge confidence out of range")

