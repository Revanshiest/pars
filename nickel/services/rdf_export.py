"""Экспорт JSON-троек в RDF и валидация SHACL."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from rdflib import Graph, Literal, Namespace, RDF, URIRef
from rdflib.namespace import OWL, RDFS, XSD

from ontology.schema import ONTOLOGY_DIR, NODE_TYPES, RELATIONS

KG = Namespace("http://rd.nickel.local/kg#")

RELATION_URI = {
    "uses_material": KG.usesMaterial,
    "operates_at_condition": KG.operatesAtCondition,
    "produces_output": KG.producesOutput,
    "described_in": KG.describedIn,
    "validated_by": KG.validatedBy,
    "contradicts": KG.contradicts,
    "located_in": KG.locatedIn,
    "has_property": KG.hasProperty,
    "part_of": KG.partOf,
    "managed_by": KG.managedBy,
    "related_to": KG.relatedTo,
    "can_substitute": KG.canSubstitute,
}

CLASS_URI = {t: KG[t] for t in NODE_TYPES}

_ONTOLOGY_PROP_KEYS = frozenset({
    "label", "confidence", "geographyTag", "sourceDocument", "sourceChunk",
    "sourcePage", "doi", "updatedAt", "version", "validFrom",
})

_SNAKE_TO_CAMEL = {
    "source_page": "sourcePage",
    "source_chunk": "sourceChunk",
    "updated_at": "updatedAt",
    "valid_from": "validFrom",
    "geography_tag": "geographyTag",
    "source_document": "sourceDocument",
}

_SKIP_PROP_KEYS = frozenset({
    "doi", "updated_at", "valid_from", "source_page", "source_chunk", "fair",
})


def _entity_uri(name: str, entity_type: str) -> URIRef:
    """Стабильный ASCII-only URI; человекочитаемое имя хранится в kg:label."""
    slug = hashlib.md5(f"{entity_type}:{name}".encode("utf-8")).hexdigest()[:12]
    et = re.sub(r"[^\w]", "_", entity_type)
    return URIRef(f"http://rd.nickel.local/entity/{et}/{slug}")


def _property_uri(key: str) -> URIRef:
    """Безопасный URI предиката: кириллица и пробелы → hash, не fragment kg#."""
    camel = _SNAKE_TO_CAMEL.get(key, key)
    if camel in _ONTOLOGY_PROP_KEYS:
        return KG[camel]
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()[:12]
    return URIRef(f"http://rd.nickel.local/prop/{digest}")


def _is_dynamic_property(key: str) -> bool:
    camel = _SNAKE_TO_CAMEL.get(key, key)
    return camel not in _ONTOLOGY_PROP_KEYS


def triples_to_graph(
    triples: List[Dict[str, Any]],
    source_document: Optional[str] = None,
) -> Graph:
    g = Graph()
    g.bind("kg", KG)
    g.parse(ONTOLOGY_DIR / "kg.ttl", format="turtle")

    for t in triples:
        subj_uri = _entity_uri(t["subject"], t["subject_type"])
        obj_uri = _entity_uri(t["object"], t["object_type"])
        rel = t["relation"]

        subj_class = CLASS_URI.get(t["subject_type"])
        obj_class = CLASS_URI.get(t["object_type"])
        if subj_class:
            g.add((subj_uri, RDF.type, subj_class))
        if obj_class:
            g.add((obj_uri, RDF.type, obj_class))

        g.add((subj_uri, KG.label, Literal(t["subject"])))
        g.add((obj_uri, KG.label, Literal(t["object"])))

        rel_uri = RELATION_URI.get(rel)
        if rel_uri:
            g.add((subj_uri, rel_uri, obj_uri))

        props = t.get("properties") or {}
        for key, val in props.items():
            if key in _SKIP_PROP_KEYS or val is None:
                continue
            prop_uri = _property_uri(key)
            g.add((subj_uri, prop_uri, Literal(str(val))))
            if _is_dynamic_property(key):
                g.add((prop_uri, RDFS.label, Literal(key)))

        if t.get("confidence") is not None:
            g.add((subj_uri, KG.confidence, Literal(float(t["confidence"]), datatype=XSD.float)))
        if t.get("geography"):
            g.add((subj_uri, KG.geographyTag, Literal(t["geography"])))
        if source_document:
            g.add((subj_uri, KG.sourceDocument, Literal(source_document)))
        if t.get("source_chunk"):
            g.add((subj_uri, KG.sourceChunk, Literal(t["source_chunk"])))
        if t.get("source_page"):
            g.add((subj_uri, KG.sourcePage, Literal(str(t["source_page"]))))
        if props.get("doi"):
            g.add((subj_uri, KG.doi, Literal(props["doi"])))
        if props.get("updated_at"):
            g.add((subj_uri, KG.updatedAt, Literal(props["updated_at"])))
        if t.get("version") is not None:
            g.add((subj_uri, KG.version, Literal(int(t["version"]), datatype=XSD.integer)))
        if props.get("valid_from"):
            g.add((subj_uri, KG.validFrom, Literal(props["valid_from"])))

    return g


def export_json_to_rdf(
    json_path: Path,
    output_path: Optional[Path] = None,
    fmt: str = "turtle",
) -> Path:
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    triples = data.get("triples", data if isinstance(data, list) else [])
    g = triples_to_graph(triples, source_document=json_path.stem)

    out = output_path or json_path.with_suffix(".ttl")
    g.serialize(destination=str(out), format=fmt)
    return out


def validate_shacl(graph: Graph) -> Dict[str, Any]:
    try:
        import pyshacl
    except ImportError:
        return {"valid": True, "warning": "pyshacl not installed, validation skipped"}

    shapes = Graph().parse(ONTOLOGY_DIR / "shapes.ttl", format="turtle")
    conforms, report_graph, report_text = pyshacl.validate(
        graph, shacl_graph=shapes, inference="rdfs", abort_on_error=False
    )
    return {
        "valid": bool(conforms),
        "report": report_text,
    }
