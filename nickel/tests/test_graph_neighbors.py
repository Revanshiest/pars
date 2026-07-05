"""Тесты быстрого обхода графа для чат-агента."""

from services.graph_view import explore_entity_neighbors


def test_list_entity_neighbor_facts(tmp_platform_db):
    store = __import__("services.store", fromlist=["get_store"]).get_store()
    store.upsert_facts([
        {
            "subject": "медь",
            "subject_type": "Material",
            "relation": "uses_material",
            "object": "electrowinning",
            "object_type": "Process",
            "confidence": 0.9,
        },
        {
            "subject": "electrowinning",
            "subject_type": "Process",
            "relation": "has_property",
            "object": "current density",
            "object_type": "Parameter",
            "confidence": 0.8,
        },
        {
            "subject": "nickel",
            "subject_type": "Material",
            "relation": "related_to",
            "object": "cathode",
            "object_type": "Product",
            "confidence": 0.5,
        },
    ], job_id="j1", source_document="demo.pdf", shacl_valid=True)

    neighbors = store.list_entity_neighbor_facts("медь", limit=10)
    assert len(neighbors) == 1
    assert neighbors[0]["object"] == "electrowinning"

    ew_neighbors = store.list_entity_neighbor_facts("electrowinning", limit=10)
    assert len(ew_neighbors) == 2


def test_explore_entity_neighbors(tmp_platform_db):
    store = __import__("services.store", fromlist=["get_store"]).get_store()
    store.upsert_facts([
        {
            "subject": "copper",
            "subject_type": "Material",
            "relation": "uses_material",
            "object": "heap leaching",
            "object_type": "Process",
        },
    ], job_id="j2", source_document="demo2.pdf", shacl_valid=True)

    result = explore_entity_neighbors("copper", limit=5)
    assert result["entity"] == "copper"
    assert len(result["edges"]) == 1
    assert result["edges"][0]["target"] == "heap leaching"
    assert result["stats"]["mode"] == "fast_neighbors"
