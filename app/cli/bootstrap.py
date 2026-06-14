import argparse
import asyncio
import json

from app.core.config import get_settings
from app.providers.dify_knowledge import DifyKnowledgeProvider
from app.providers.neo4j_graph import Neo4jGraphProvider


async def bootstrap_dify() -> dict[str, object]:
    settings = get_settings()
    provider = DifyKnowledgeProvider(settings)
    try:
        fields = await provider.ensure_metadata_fields()
        return {"ok": True, "provider": "dify", "metadata_fields": fields}
    finally:
        await provider.close()


async def bootstrap_neo4j() -> dict[str, object]:
    settings = get_settings()
    provider = Neo4jGraphProvider(settings)
    try:
        await provider.initialize()
        return {"ok": True, "provider": "neo4j", "constraints": ["entity_uid", "relates_to_edge_key_if_supported"]}
    finally:
        await provider.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap external providers")
    parser.add_argument("provider", choices=["dify", "neo4j"])
    args = parser.parse_args()
    result = asyncio.run(bootstrap_dify() if args.provider == "dify" else bootstrap_neo4j())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
