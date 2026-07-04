"""Быстрый импорт готового JSON графа в Neo4j + SQLite + Qdrant (без LLM/BGE entity resolution)."""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

from ontology.schema import filter_valid_triples
from services.fair_metadata import attach_provenance, build_fair_metadata
from services.json_ingest import load_triples_json, parse_json_upload
from services.neo4j_loader import Neo4jLoader
from services.qdrant_index import QdrantIndexer
from services.store import get_store


def _sanitize_props(props: dict) -> dict:
    """Neo4j: только примитивы в map-свойствах, без null."""
    out: dict = {}
    for k, v in (props or {}).items():
        if v is None:
            continue
        if isinstance(v, bool):
            out[k] = v
        elif isinstance(v, (int, float)):
            out[k] = v
        elif isinstance(v, dict):
            out[k] = json.dumps(v, ensure_ascii=False)
        elif isinstance(v, list):
            out[k] = [
                json.dumps(x, ensure_ascii=False) if isinstance(x, dict) else x
                for x in v
                if x is not None
            ]
        else:
            out[k] = str(v)
    return out


def _prepare_triple(t: dict) -> dict:
    t = dict(t)
    props = _sanitize_props(t.get("properties") or {})
    if "confidence" in props:
        try:
            props["confidence"] = float(props["confidence"])
        except (TypeError, ValueError):
            pass
    t["properties"] = props
    if t.get("confidence") is not None:
        try:
            t["confidence"] = float(t["confidence"])
        except (TypeError, ValueError):
            pass
    return t


def _dedupe(triples: list) -> list:
    seen: set[tuple] = set()
    out = []
    for t in triples:
        key = (t.get("subject"), t.get("relation"), t.get("object"))
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def _seed_glossary(triples: list, store) -> int:
    index = store.build_glossary_index()
    added = 0
    for t in triples:
        for name, etype in [
            (t.get("subject"), t.get("subject_type")),
            (t.get("object"), t.get("object_type")),
        ]:
            if not name or len(str(name)) <= 2:
                continue
            key = str(name).strip().lower()
            if key in index:
                continue
            store.add_glossary_term(
                {
                    "canonical": str(name).strip(),
                    "synonyms_ru": [],
                    "synonyms_en": [],
                    "domain": etype or "Concept",
                    "definition": "Импортировано из JSON графа",
                },
                source="json_import",
            )
            index[key] = str(name).strip()
            added += 1
    return added


def import_graph(filepath: str) -> dict:
    kind, payload = parse_json_upload(filepath)
    if kind != "triples":
        raise ValueError(f"Expected triples JSON, got: {kind}")

    triples, document_metadata = load_triples_json(payload)
    triples = filter_valid_triples(triples)
    triples = _dedupe(triples)

    job_id = str(uuid.uuid4())
    basename = Path(filepath).stem.replace("_yandex_graph", "").replace("_graph", "")
    store = get_store()

    fair = build_fair_metadata(
        source_document=basename,
        job_id=job_id,
        document_kind=document_metadata.get("document_kind", "publication"),
        source_file_path=document_metadata.get("source_file", basename),
    )
    document_metadata.setdefault("source_file", document_metadata.get("source_file", basename + ".pdf"))
    document_metadata["fair"] = fair

    for t in triples:
        t.setdefault("confidence", 0.85)
        t.setdefault("verification_status", "pending")
        t.setdefault("geography", document_metadata.get("literature_type", "EN"))

    triples = [_prepare_triple(t) for t in triples]
    triples = attach_provenance(triples, source_document=basename, job_id=job_id, fair=fair, chunks=[])
    triples = [_prepare_triple(t) for t in triples]

    store.register_document(
        job_id,
        basename,
        document_kind=document_metadata.get("document_kind", "publication"),
        metadata=document_metadata,
    )
    store.upsert_facts(triples, job_id=job_id, source_document=basename, shacl_valid=True)
    glossary_added = _seed_glossary(triples, store)

    neo4j_stats: dict = {}
    with Neo4jLoader() as loader:
        loader.init_schema()
        neo4j_stats = loader.load_triples(triples, job_id=job_id, source_document=basename)

    qdrant_stats: dict = {"entities": 0}
    try:
        entities: dict = {}
        for t in triples:
            entities[(t["subject"], t["subject_type"])] = {
                "name": t["subject"],
                "type": t["subject_type"],
            }
            entities[(t["object"], t["object_type"])] = {
                "name": t["object"],
                "type": t["object_type"],
            }
        indexer = QdrantIndexer()
        qdrant_stats["entities"] = indexer.index_entities(
            list(entities.values()), job_id, metadata={"source": basename}
        )
    except Exception as e:
        qdrant_stats["error"] = str(e)

    return {
        "job_id": job_id,
        "source": basename,
        "triples_loaded": len(triples),
        "glossary_terms_added": glossary_added,
        "neo4j": neo4j_stats,
        "qdrant": qdrant_stats,
    }


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "/app/data/uploads/schlesinger_graph.json"
    result = import_graph(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
