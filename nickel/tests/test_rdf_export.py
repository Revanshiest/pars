"""RDF export: кириллица и пробелы в properties не ломают Turtle."""

from __future__ import annotations

from services.rdf_export import triples_to_graph


def test_cyrillic_property_key_serializes():
    triples = [{
        "subject": "Медный купорос",
        "subject_type": "Material",
        "relation": "has_property",
        "object": "Нераств. в воде остатка",
        "object_type": "Parameter",
        "properties": {
            "Нераств.в воде остатка": "0.05%",
            "value": "99.5",
        },
        "confidence": 0.8,
    }]
    g = triples_to_graph(triples, source_document="test.pdf")
    ttl = g.serialize(format="turtle")
    assert isinstance(ttl, str)
    assert "Нераств" in ttl or "0.05" in ttl
    assert "http://rd.nickel.local/kg#Нераств" not in ttl
