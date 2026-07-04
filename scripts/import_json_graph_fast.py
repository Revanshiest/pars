"""Быстрый импорт готового JSON графа в Neo4j + SQLite (+ опционально Qdrant)."""
from __future__ import annotations

import json
import sys

from services.json_graph_import import import_triples_json_file


def import_graph(filepath: str) -> dict:
    import uuid
    return import_triples_json_file(filepath, job_id=str(uuid.uuid4()))


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "/app/data/uploads/schlesinger_graph.json"
    result = import_graph(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
