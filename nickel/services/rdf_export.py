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


def _uri_slug(name: str, max_len: int = 40) -> str:
    """Path-safe ASCII slug; original label is stored in kg:label."""
    s = name.replace(" ", "_")
    s = re.sub(r"[^\w\-.]", "_", s, flags=re.UNICODE)
    s = re.sub(r"_+", "_", s).strip("_")
    return (s[:max_len] or "entity")


def _entity_uri(name: str, entity_type: str) -> URIRef:
    slug = hashlib.md5(f"{entity_type}:{name}".encode()).hexdigest()[:12]
    safe = _uri_slug(name)
    return URIRef(f"http://rd.nickel.local/entity/{entity_type}/{safe}_{slug}")


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
            g.add((subj_uri, KG[key], Literal(str(val))))

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
