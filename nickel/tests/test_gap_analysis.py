"""Тесты gap analysis и platform config."""

from services.gap_analysis import analyze_scenario, discover_gap_scenarios, parse_gap_query
from services.platform_config import domain_processes, search_examples


def test_domain_processes_from_config():
    domains = domain_processes()
    assert "гидрометаллургия" in domains
    assert "выщелачивание" in domains["гидрометаллургия"]


def test_search_examples_from_config():
    examples = search_examples()
    assert len(examples) >= 3
    assert any("материал" in e.lower() or "обзор" in e.lower() or "электро" in e.lower() for e in examples)


def test_discover_gap_scenarios_empty():
    scenarios = discover_gap_scenarios([])
    assert isinstance(scenarios, list)


def test_analyze_scenario_gap():
    facts = [
        {
            "subject": "никель",
            "subject_type": "Material",
            "relation": "uses_material",
            "object": "выщелачивание",
            "object_type": "Process",
            "geography": "RU",
            "properties": {},
        },
    ]
    scenario = {
        "id": "test",
        "label": "никель + выщелачивание + холод",
        "dimensions": {
            "Material": ["никель"],
            "Process": ["выщелачивание"],
            "Geography": ["холод", "cold"],
        },
    }
    result = analyze_scenario(facts, scenario)
    assert result["coverage"]["Material"] >= 1
    assert result["coverage"]["Process"] >= 1
    assert result["is_gap"] is True


def test_parse_gap_query_glossary():
    parsed = parse_gap_query("электроэкстракция никеля в холодном климате")
    assert parsed.get("material") or parsed.get("process") or parsed.get("climate")
