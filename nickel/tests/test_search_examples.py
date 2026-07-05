"""Тесты генерации примеров вопросов для чата."""

from services.search_examples_builder import graph_search_examples


def test_graph_search_examples_from_facts(tmp_platform_db):
    store = __import__("services.store", fromlist=["get_store"]).get_store()
    store.upsert_facts([
        {
            "subject": "медь",
            "subject_type": "Material",
            "relation": "uses_material",
            "object": "electrowinning",
            "object_type": "Process",
            "geography": "RU",
            "properties": {"description": "электроэкстракция меди"},
        },
        {
            "subject": "electrowinning",
            "subject_type": "Process",
            "relation": "has_property",
            "object": "% Cu in ore",
            "object_type": "Parameter",
            "geography": "EN",
            "properties": {"value": "0.7%"},
        },
        {
            "subject": "heap leaching",
            "subject_type": "Process",
            "relation": "operates_at_condition",
            "object": "кучное выщелачивание",
            "object_type": "Process",
            "properties": {},
        },
    ], job_id="j1", source_document="demo.pdf", shacl_valid=True)

    examples = graph_search_examples(limit=5)
    assert len(examples) >= 2
    assert not any("какие связи" in e.lower() for e in examples)
    assert any(
        any(kw in e.lower() for kw in ("электроэкстрак", "мед", "copper", "cu", "выщелач", "leach"))
        for e in examples
    )
