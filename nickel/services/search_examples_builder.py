"""Примеры вопросов для чат-бота в стиле экспертных запросов — только по темам из графа."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from services.platform_config import search_examples as config_search_examples
from services.store import get_store

CompareHint = Optional[str]


@dataclass(frozen=True)
class ExpertTopic:
    id: str
    keywords: Tuple[str, ...]
    min_hits: int
    priority: int
    build: Callable[[List[Dict[str, Any]], CompareHint], Optional[str]]


def _fact_blob(fact: Dict[str, Any]) -> str:
    props = fact.get("properties") or {}
    parts = [
        fact.get("subject") or "",
        fact.get("object") or "",
        fact.get("relation") or "",
        fact.get("geography") or "",
        props.get("description") or "",
        str(props.get("value") or ""),
        props.get("document_kind") or "",
    ]
    return " ".join(str(p) for p in parts if p).lower()


def _match_facts(facts: Sequence[Dict[str, Any]], keywords: Sequence[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for f in facts:
        blob = _fact_blob(f)
        if any(kw in blob for kw in keywords):
            out.append(f)
    return out


def _compare_hint(facts: Sequence[Dict[str, Any]]) -> CompareHint:
    geos = {(f.get("geography") or "").upper() for f in facts}
    has_ru = "RU" in geos
    has_global = bool(geos & {"EN", "GLOBAL", "US", "EU", "CN"})
    if has_ru and has_global:
        return "Отечественная и мировая практика по загруженным материалам."
    if has_ru:
        return "По отечественным источникам в базе."
    if has_global:
        return "По зарубежным источникам в базе."
    return None


def _top_names(
    facts: Sequence[Dict[str, Any]],
    types: Sequence[str] = ("Process", "Material", "Parameter", "Equipment"),
    limit: int = 2,
) -> List[str]:
    from collections import Counter

    counter: Counter[str] = Counter()
    type_set = set(types)
    for f in facts:
        for side in ("subject", "object"):
            if f.get(f"{side}_type") not in type_set:
                continue
            name = (f.get(side) or "").strip()
            if name and len(name) <= 80:
                counter[name] += 1
    return [n for n, _ in counter.most_common(limit)]


def _join_ru(names: List[str]) -> str:
    if not names:
        return ""
    if len(names) == 1:
        return f"«{names[0]}»"
    return f"«{names[0]}» и «{names[1]}»"


def _with_compare(question: str, hint: CompareHint) -> str:
    if not hint:
        return question
    return f"{question} {hint}"


def _q_desalination(facts: List[Dict[str, Any]], hint: CompareHint) -> Optional[str]:
    params = _top_names(facts, ("Parameter", "Metric", "Process"), limit=2)
    extra = f" Упомянуты: {_join_ru(params)}." if params else ""
    return _with_compare(
        "Какие варианты подготовки и обессоливания воды для горно-металлургических "
        "предприятий (обогатительная фабрика) описаны в загруженных материалах? "
        "Интересуют требования к сульфатам, хлоридам и сухому остатку порядка 200–300 мг/л."
        + extra,
        hint,
    )


def _q_mine_water_review(facts: List[Dict[str, Any]], hint: CompareHint) -> Optional[str]:
    processes = _top_names(facts, ("Process",), limit=2)
    extra = f" Основные процессы в базе: {_join_ru(processes)}." if processes else ""
    return _with_compare(
        "Сделай обзор методов очистки шахтных вод горно-рудных предприятий цветной "
        "металлургии по загруженным источникам." + extra,
        hint,
    )


def _q_catholyte_nickel(facts: List[Dict[str, Any]], hint: CompareHint) -> Optional[str]:
    items = _top_names(facts, ("Process", "Equipment", "Parameter"), limit=3)
    extra = f" В базе: {_join_ru(items)}." if items else ""
    return _with_compare(
        "Какие технические решения по организации циркуляции католита при производстве "
        "никелевых катодов методом электроэкстракции описаны в материалах?" + extra,
        hint,
    )


def _q_electrolyte_systems(facts: List[Dict[str, Any]], hint: CompareHint) -> Optional[str]:
    metals = []
    for token in ("никель", "nickel", "медь", "copper", "кобальт", "cobalt"):
        if any(token in _fact_blob(f) for f in facts):
            metals.append(token)
    metal_phrase = ", ".join(dict.fromkeys(metals)[:3]) if metals else "никеля и меди"
    return _with_compare(
        f"Обзор по загруженным материалам: как организованы подача электролита в ванны, "
        f"движение потока, циркуляция и вывод раствора при электролитическом производстве "
        f"({metal_phrase})? Есть ли данные по диафрагменным ячейкам?",
        hint,
    )


def _q_gypsum(facts: List[Dict[str, Any]], hint: CompareHint) -> Optional[str]:
    mats = _top_names(facts, ("Material", "Process"), limit=2)
    extra = f" Упоминаются: {_join_ru(mats)}." if mats else ""
    return _with_compare(
        "Какие источники техногенного гипса и способы его переработки описаны "
        "в загруженных документах?" + extra,
        hint,
    )


def _q_injection(facts: List[Dict[str, Any]], hint: CompareHint) -> Optional[str]:
    return _with_compare(
        "Какие технологии и примеры закачки шахтных вод в глубокие горизонты "
        "приведены в загруженных материалах?",
        hint,
    )


def _q_coal_backfill(facts: List[Dict[str, Any]], hint: CompareHint) -> Optional[str]:
    return _with_compare(
        "Какие практики использования угля и отходов угольной промышленности "
        "для закладки выработанного пространства есть в базе?",
        hint,
    )


def _q_so2(facts: List[Dict[str, Any]], hint: CompareHint) -> Optional[str]:
    procs = _top_names(facts, ("Process", "Equipment"), limit=2)
    extra = f" Связанные решения: {_join_ru(procs)}." if procs else ""
    return _with_compare(
        "Какие способы удаления SO₂ из отходящих газов металлургических "
        "предприятий описаны в загруженных источниках?" + extra,
        hint,
    )


def _q_precious_distribution(facts: List[Dict[str, Any]], hint: CompareHint) -> Optional[str]:
    mats = _top_names(facts, ("Material",), limit=2)
    extra = f" Материалы: {_join_ru(mats)}." if mats else ""
    return _with_compare(
        "Что в базе известно о распределении Au, Ag и МПГ между медным/никелевым "
        "штейном и шлаком?" + extra,
        hint,
    )


def _q_lead_zinc(facts: List[Dict[str, Any]], hint: CompareHint) -> Optional[str]:
    procs = _top_names(facts, ("Process",), limit=2)
    extra = f" Процессы: {_join_ru(procs)}." if procs else ""
    return _with_compare(
        "Какие современные способы переработки свинцово-цинкового сырья "
        "описаны в загруженных материалах?" + extra,
        hint,
    )


def _q_copper_ew(facts: List[Dict[str, Any]], hint: CompareHint) -> Optional[str]:
    params = _top_names(facts, ("Parameter", "Metric"), limit=2)
    extra = f" Параметры: {_join_ru(params)}." if params else ""
    return _with_compare(
        "Какие данные по электроэкстракции меди и содержанию Cu в сырье/концентрате "
        "есть в загруженных материалах?" + extra,
        hint,
    )


def _q_heap_leaching(facts: List[Dict[str, Any]], hint: CompareHint) -> Optional[str]:
    return _with_compare(
        "Какие технологии кучного выщелачивания и связанные параметры процесса "
        "описаны в загруженных документах?",
        hint,
    )


EXPERT_TOPICS: Tuple[ExpertTopic, ...] = (
    ExpertTopic("desalination", ("обессолив", "desalination", "сульфат", "sulfate", "хлорид", "chloride", "сухой остаток", "скважин"), 2, 1, _q_desalination),
    ExpertTopic("mine_water", ("шахтн", "mine water", "очистк", "водоподготов", "дренаж"), 2, 2, _q_mine_water_review),
    ExpertTopic("catholyte", ("католит", "catholyte", "катод", "electrowinning", "электроэкстракц"), 2, 3, _q_catholyte_nickel),
    ExpertTopic("electrolyte", ("электролит", "electrolyte", "диафрагм", "diaphragm", "ванн", "cell", "циркуляц"), 2, 4, _q_electrolyte_systems),
    ExpertTopic("gypsum", ("гипс", "gypsum", "phosphogypsum", "техноген"), 2, 5, _q_gypsum),
    ExpertTopic("injection", ("закачк", "injection", "глубок", "горизонт", "aquifer"), 2, 6, _q_injection),
    ExpertTopic("coal_backfill", ("уголь", "coal", "закладк", "backfill", "goaf"), 2, 7, _q_coal_backfill),
    ExpertTopic("so2", ("so2", "so₂", "сернист", "desulfur", "отходящ", "flue gas"), 2, 8, _q_so2),
    ExpertTopic("precious", ("золот", "сереб", "gold", "silver", "pgm", "platino", "precious", "штейн", "matte", "шлак", "slag"), 2, 9, _q_precious_distribution),
    ExpertTopic("lead_zinc", ("свинец", "lead", "цинк", "zinc", "pb", "zn"), 2, 10, _q_lead_zinc),
    ExpertTopic("copper_ew", ("мед", "copper", " cu", "%cu", "electrowinning", "кathode"), 2, 11, _q_copper_ew),
    ExpertTopic("heap_leach", ("heap leach", "кучн", "выщелач", "leaching", "lixiviant"), 2, 12, _q_heap_leaching),
)


def _fallback_from_entities(facts: List[Dict[str, Any]], limit: int) -> List[str]:
    from collections import Counter

    counter: Counter[str] = Counter()
    etypes: Dict[str, str] = {}
    for f in facts:
        for side in ("subject", "object"):
            name = (f.get(side) or "").strip()
            if not name or len(name) > 72:
                continue
            counter[name] += 1
            etypes[name] = f.get(f"{side}_type") or etypes.get(name, "Concept")

    examples: List[str] = []
    for name, _ in counter.most_common(20):
        etype = etypes.get(name, "Concept")
        if etype == "Process":
            q = f"Какие технические решения и параметры процесса «{name}» описаны в загруженных материалах?"
        elif etype == "Material":
            q = f"Какие технологии переработки и свойства материала «{name}» есть в базе?"
        elif etype == "Parameter":
            q = f"Какие значения и условия для параметра «{name}» приведены в загруженных источниках?"
        else:
            q = f"Что известно по теме «{name}» в загруженных материалах?"
        if q not in examples:
            examples.append(q)
        if len(examples) >= limit:
            break
    return examples


def graph_search_examples(limit: int = 5) -> List[str]:
    """Экспертные вопросы только по темам, подтверждённым фактами в графе."""
    facts = get_store().list_facts(limit=5000)
    if not facts:
        return list(config_search_examples())[:limit]

    examples: List[str] = []
    seen_ids: set[str] = set()

    for topic in sorted(EXPERT_TOPICS, key=lambda t: t.priority):
        matched = _match_facts(facts, topic.keywords)
        if len(matched) < topic.min_hits:
            continue
        hint = _compare_hint(matched)
        question = topic.build(matched, hint)
        if question and topic.id not in seen_ids:
            examples.append(question)
            seen_ids.add(topic.id)
        if len(examples) >= limit:
            return examples[:limit]

    if len(examples) < limit:
        for q in _fallback_from_entities(facts, limit - len(examples)):
            if q not in examples:
                examples.append(q)

    if examples:
        return examples[:limit]

    return list(config_search_examples())[:limit]
