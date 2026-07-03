"""Инструменты агента: hybrid search + обход графа Neo4j."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.hybrid_search import hybrid_ranked_search
from services.neo4j_loader import Neo4jLoader
from services.search_filters import compare_practices


class SearchTools:
    """Набор инструментов для RAG-агента поверх hybrid pipeline, Qdrant и Neo4j."""

    TOOL_DEFINITIONS = [
        {
            "name": "hybrid_search",
            "description": (
                "Единый ranked pipeline: vector search по чанкам и сущностям + "
                "факты из SQLite + graph traversal Neo4j. Поддерживает фильтры."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 12},
                    "entity_type": {"type": "string"},
                    "geography": {"type": "string", "enum": ["RU", "EN", "global"]},
                    "document_kind": {"type": "string"},
                    "year_from": {"type": "integer"},
                    "year_to": {"type": "integer"},
                    "author": {"type": "string"},
                },
                "required": ["query"],
            },
        },
        {
            "name": "compare_practices",
            "description": (
                "Сравнение отечественной (RU) и мировой (EN/global) практики по теме."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        },
        {
            "name": "explore_graph",
            "description": "Обход графа Neo4j от сущности.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_name": {"type": "string"},
                    "depth": {"type": "integer", "default": 2},
                },
                "required": ["entity_name"],
            },
        },
        {
            "name": "graph_stats",
            "description": "Статистика графа: количество сущностей и связей.",
            "parameters": {"type": "object", "properties": {}},
        },
    ]

    def __init__(self):
        self._neo4j: Optional[Neo4jLoader] = None

    @property
    def neo4j(self) -> Neo4jLoader:
        if self._neo4j is None:
            self._neo4j = Neo4jLoader()
        return self._neo4j

    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        handlers = {
            "hybrid_search": self._hybrid_search,
            "compare_practices": self._compare_practices,
            "explore_graph": self._explore_graph,
            "graph_stats": self._graph_stats,
            # backward compatibility
            "search_document_chunks": self._hybrid_search,
            "search_entities": self._hybrid_search,
            "filter_by_geography": self._compare_practices,
        }
        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}
        try:
            return handler(arguments)
        except Exception as e:
            return {"error": str(e), "tool": tool_name}

    def _hybrid_search(self, args: Dict) -> Dict:
        result = hybrid_ranked_search(
            args["query"],
            limit=args.get("limit", 12),
            entity_type=args.get("entity_type"),
            geography=args.get("geography"),
            document_kind=args.get("document_kind"),
            year_from=args.get("year_from"),
            year_to=args.get("year_to"),
            author=args.get("author"),
            min_confidence=args.get("min_confidence"),
            verification_status=args.get("verification_status"),
        )
        return {
            "results": result.get("ranked_results", []),
            "chunks": result.get("chunks", []),
            "entities": result.get("entities", []),
            "verified_facts": result.get("verified_facts", []),
            "pipeline": result.get("pipeline"),
            "count": len(result.get("ranked_results", [])),
        }

    def _compare_practices(self, args: Dict) -> Dict:
        return compare_practices(
            args["query"],
            limit=args.get("limit", 10),
            document_kind=args.get("document_kind"),
            year_from=args.get("year_from"),
            year_to=args.get("year_to"),
            author=args.get("author"),
        )

    def _explore_graph(self, args: Dict) -> Dict:
        neighbors = self.neo4j.search_neighbors(
            args["entity_name"], depth=args.get("depth", 2)
        )
        return {"entity": args["entity_name"], "neighbors": neighbors}

    def _graph_stats(self, _args: Dict) -> Dict:
        return self.neo4j.stats()
