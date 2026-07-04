"""Единый источник истины для онтологии R&D Knowledge Graph."""

from pathlib import Path
from typing import List, Literal, Optional, Dict

from pydantic import BaseModel, Field

ONTOLOGY_DIR = Path(__file__).parent

NODE_TYPES: List[str] = [
    "Material",
    "Equipment",
    "Process",
    "Parameter",
    "Metric",
    "Property",
    "Facility",
    "Expert",
    "Regulation",
    "Publication",
    "Geography",
    "Document",
    "Concept",
    "Product",
    "Experiment",
]

RELATIONS: List[str] = [
    "uses_material",
    "operates_at_condition",
    "produces_output",
    "described_in",
    "validated_by",
    "contradicts",
    "located_in",
    "has_property",
    "part_of",
    "managed_by",
    "related_to",
    "can_substitute",
]

RELATION_META: Dict[str, Dict[str, str]] = {
    "uses_material": {
        "label_ru": "использует материал",
        "description": "Процесс, установка или эксперимент применяет данный материал",
    },
    "operates_at_condition": {
        "label_ru": "работает при условии",
        "description": "Режим или параметры эксплуатации (температура, давление, расход)",
    },
    "produces_output": {
        "label_ru": "даёт продукт",
        "description": "Процесс или установка производит выходной продукт или поток",
    },
    "described_in": {
        "label_ru": "описано в",
        "description": "Сущность упоминается в публикации, отчёте или документе",
    },
    "validated_by": {
        "label_ru": "подтверждено",
        "description": "Вывод или факт подтверждён экспертом, нормативом или экспериментом",
    },
    "contradicts": {
        "label_ru": "противоречит",
        "description": "Конфликтующие выводы или несовместимые данные",
    },
    "located_in": {
        "label_ru": "расположено в",
        "description": "Географическая или производственная привязка",
    },
    "has_property": {
        "label_ru": "имеет свойство",
        "description": "Числовой или качественный параметр материала/объекта",
    },
    "part_of": {
        "label_ru": "часть",
        "description": "Компонент входит в состав системы или установки",
    },
    "managed_by": {
        "label_ru": "управляется",
        "description": "Объект находится под управлением эксперта, лаборатории или подразделения",
    },
    "related_to": {
        "label_ru": "связано с",
        "description": "Общая ассоциативная связь без уточнённой семантики",
    },
    "can_substitute": {
        "label_ru": "может заменить",
        "description": "Альтернативный материал, технология или решение",
    },
}

NodeType = Literal[
    "Material", "Equipment", "Process", "Parameter", "Metric",
    "Property", "Facility", "Expert", "Regulation", "Publication",
    "Geography", "Document", "Concept", "Product", "Experiment",
]

RelationType = Literal[
    "uses_material", "operates_at_condition", "produces_output",
    "described_in", "validated_by", "contradicts", "located_in",
    "has_property", "part_of", "managed_by", "related_to", "can_substitute",
]


class Triple(BaseModel):
    subject: str = Field(description="Имя субъекта")
    subject_type: str = Field(description="Тип субъекта из онтологии")
    relation: str = Field(description="Тип связи из онтологии")
    object: str = Field(description="Имя объекта")
    object_type: str = Field(description="Тип объекта из онтологии")
    properties: dict = Field(default_factory=dict, description="Числовые ограничения, условия, метаданные")
    source_chunk: Optional[str] = Field(default=None, description="ID чанка-источника")
    version: Optional[int] = Field(default=1, description="Номер версии факта")
    doi: Optional[str] = Field(default=None, description="DOI источника")
    source_page: Optional[str] = Field(default=None, description="Страница источника")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    geography: Optional[str] = Field(default=None, description="RU / EN / global")


class ExtractionResult(BaseModel):
    triples: List[Triple] = Field(default_factory=list)


def is_valid_triple(triple: dict) -> bool:
    return (
        triple.get("relation") in RELATIONS
        and triple.get("subject_type") in NODE_TYPES
        and triple.get("object_type") in NODE_TYPES
    )


def filter_valid_triples(triples: List[dict]) -> List[dict]:
    return [t for t in triples if is_valid_triple(t)]


# Алиасы для обратной совместимости с pipeline_mvp / orchestrator
ALLOWED_NODE_TYPES = NODE_TYPES
ALLOWED_RELATIONS = RELATIONS
