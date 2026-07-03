"""Regex-извлечение и валидация концентраций, температур, расходов, диапазонов."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# нормализация единиц → канонический вид
UNIT_ALIASES = {
    "мг/л": "mg/l", "mg/l": "mg/l", "mg/L": "mg/l", "мг/дм3": "mg/l", "мг/дм³": "mg/l",
    "ppm": "mg/l", "g/l": "g/l", "г/л": "g/l", "kg/m3": "kg/m3", "кг/м3": "kg/m3",
    "°c": "C", "c": "C", "°с": "C", "℃": "C",
    "л/мин": "L/min", "l/min": "L/min", "m3/h": "m3/h", "м3/ч": "m3/h",
    "т/сут": "t/d", "t/d": "t/d", "t/day": "t/d",
    "%": "%", "percent": "%",
}

PARAMETER_ALIASES = {
    "so4": "сульфаты", "sulfate": "сульфаты", "sulfates": "сульфаты", "сульфат": "сульфаты",
    "cl": "хлориды", "chloride": "хлориды", "chlorides": "хлориды", "хлорид": "хлориды",
    "ca": "кальций", "calcium": "кальций", "кальций": "кальций",
    "mg": "магний", "magnesium": "магний", "магний": "магний",
    "na": "натрий", "sodium": "натрий", "натрий": "натрий",
    "сухой остаток": "сухой остаток", "dry residue": "сухой остаток", "tds": "сухой остаток",
    "температура": "температура", "temperature": "температура", "temp": "температура",
    "скорость потока": "скорость потока", "flow rate": "скорость потока", "flow": "скорость потока",
    "концентрация": "концентрация", "concentration": "концентрация",
}

# parameter context (optional prefix) + operator + value + unit
PATTERNS = [
    # ≤300 мг/л, < 200 mg/L, >= 150°C
    re.compile(
        r"(?P<prefix>[\wа-яёА-ЯЁ\s\-]{0,40}?)"
        r"(?P<op>[≤≥<>]=?|=)\s*"
        r"(?P<val>\d+(?:[.,]\d+)?)\s*"
        r"(?P<unit>(?:мг/л|mg/l|mg/L|мг/дм[3³]|ppm|g/l|г/л|°?[cсCС]|%|л/мин|l/min|m3/h|м3/ч|т/сут|t/d|kg/m3|кг/м3))",
        re.IGNORECASE,
    ),
    # 200-300 мг/л (диапазон)
    re.compile(
        r"(?P<prefix>[\wа-яёА-ЯЁ\s\-]{0,40}?)"
        r"(?P<val_min>\d+(?:[.,]\d+)?)\s*[-–—]\s*"
        r"(?P<val_max>\d+(?:[.,]\d+)?)\s*"
        r"(?P<unit>(?:мг/л|mg/l|mg/L|мг/дм[3³]|ppm|g/l|г/л|°?[cсCС]|%|л/мин|l/min|m3/h|м3/ч|т/сут|t/d))",
        re.IGNORECASE,
    ),
    # 150°C, 100 mg/l (без оператора)
    re.compile(
        r"(?P<prefix>[\wа-яёА-ЯЁ\s\-]{0,40}?)"
        r"(?P<val>\d+(?:[.,]\d+)?)\s*"
        r"(?P<unit>(?:мг/л|mg/l|mg/L|мг/дм[3³]|ppm|g/l|г/л|°?[cсCС]|%|л/мин|l/min|m3/h|м3/ч|т/сут|t/d))",
        re.IGNORECASE,
    ),
]

OP_MAP = {"<": "<", ">": ">", "<=": "<=", ">=": ">=", "=<": "<=", "=>": ">=",
          "≤": "<=", "≥": ">=", "=": "=", "==": "="}


def _parse_float(s: str) -> float:
    return float(s.replace(",", "."))


def _normalize_unit(raw: str) -> str:
    key = raw.lower().replace(" ", "").replace("°", "")
    for alias, canon in UNIT_ALIASES.items():
        if alias.replace("°", "").replace(" ", "") == key or alias.lower() == raw.lower():
            return canon
    return raw.lower()


def _normalize_parameter(prefix: str, fallback: str = "") -> str:
    text = (prefix or fallback).strip().lower()
    text = re.sub(r"\s+", " ", text)
    for alias, canon in PARAMETER_ALIASES.items():
        if alias in text or text.endswith(alias):
            return canon
    # последнее значимое слово
    words = [w for w in re.findall(r"[\wа-яё]+", text) if len(w) > 2]
    return words[-1] if words else (fallback or "концентрация")


def extract_numeric_constraints(text: str) -> List[Dict[str, Any]]:
    """Извлекает структурированные числовые ограничения из текста."""
    found: List[Dict[str, Any]] = []
    seen = set()

    for pattern in PATTERNS:
        for m in pattern.finditer(text):
            g = m.groupdict()
            raw = m.group(0).strip()
            if raw in seen:
                continue
            seen.add(raw)

            unit = _normalize_unit(g.get("unit") or "")
            param = _normalize_parameter(g.get("prefix") or "")

            if g.get("val_min") and g.get("val_max"):
                constraint = {
                    "parameter": param,
                    "operator": "range",
                    "value": None,
                    "value_min": _parse_float(g["val_min"]),
                    "value_max": _parse_float(g["val_max"]),
                    "unit": unit,
                    "raw_text": raw,
                    "validated": True,
                }
            else:
                op = OP_MAP.get(g.get("op") or "=", "=")
                constraint = {
                    "parameter": param,
                    "operator": op,
                    "value": _parse_float(g["val"]),
                    "value_min": None,
                    "value_max": None,
                    "unit": unit,
                    "raw_text": raw,
                    "validated": True,
                }
            found.append(constraint)
    return found


def parse_numeric_query(query: str) -> Optional[Dict[str, Any]]:
    """Парсит запрос вида «сульфаты < 200 мг/л»."""
    q = query.strip()
    # явный паттерн: параметр + оператор + число + единица
    m = re.search(
        r"(?P<param>[\wа-яёА-ЯЁ\s]+?)\s*"
        r"(?P<op>[≤≥<>]=?)\s*"
        r"(?P<val>\d+(?:[.,]\d+)?)\s*"
        r"(?P<unit>(?:мг/л|mg/l|mg/L|мг/дм[3³]|ppm|g/l|г/л|°?[cсCС]|%|л/мин|l/min|m3/h|т/сут|t/d|kg/m3)?)",
        q, re.IGNORECASE,
    )
    if m:
        param = _normalize_parameter(m.group("param"))
        return {
            "parameter": param,
            "operator": OP_MAP.get(m.group("op"), m.group("op")),
            "value": _parse_float(m.group("val")),
            "unit": _normalize_unit(m.group("unit") or "mg/l"),
            "raw_query": q,
        }

    constraints = extract_numeric_constraints(q)
    if constraints:
        c = constraints[0]
        return {
            "parameter": c["parameter"],
            "operator": c["operator"],
            "value": c.get("value"),
            "value_min": c.get("value_min"),
            "value_max": c.get("value_max"),
            "unit": c["unit"],
            "raw_query": q,
        }
    return None


def validate_and_merge_properties(
    properties: Dict[str, Any],
    source_text: str = "",
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Валидирует LLM-properties и дополняет regex-извлечением."""
    props = dict(properties or {})
    constraints: List[Dict[str, Any]] = list(props.get("numeric_constraints") or [])

    # сканируем строковые значения properties
    scan_text = source_text + " " + " ".join(str(v) for v in props.values())
    extracted = extract_numeric_constraints(scan_text)

    for c in extracted:
        if not any(e["raw_text"] == c["raw_text"] for e in constraints):
            constraints.append(c)

    # нормализуем одиночные value/temperature/concentration из LLM
    for key in ("value", "concentration", "temperature", "temperature_c", "flow_rate"):
        if key in props:
            try:
                val = _parse_float(str(props[key]).replace(",", ".").rstrip("°Ccf"))
                unit = "C" if "temp" in key else props.get("unit", "mg/l")
                param = _normalize_parameter(key, props.get("parameter", key))
                constraints.append({
                    "parameter": param,
                    "operator": "=",
                    "value": val,
                    "unit": _normalize_unit(str(unit)),
                    "raw_text": f"{key}={props[key]}",
                    "validated": True,
                    "source": "llm_property",
                })
            except ValueError:
                props[f"{key}_invalid"] = props[key]

    props["numeric_constraints"] = constraints
    return props, constraints


def enrich_triples_with_numerics(
    triples: List[Dict[str, Any]],
    document_text: str = "",
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    stats = {"constraints_added": 0, "triples_enriched": 0}
    for t in triples:
        props, constraints = validate_and_merge_properties(
            t.get("properties") or {},
            document_text,
        )
        t["properties"] = props
        if constraints:
            stats["triples_enriched"] += 1
            stats["constraints_added"] += len(constraints)
    return triples, stats


def constraint_matches_query(constraint: Dict, query: Dict) -> bool:
    """Проверяет, удовлетворяет ли constraint числовому запросу."""
    if constraint.get("parameter") and query.get("parameter"):
        p1 = constraint["parameter"].lower()
        p2 = query["parameter"].lower()
        if p1 not in p2 and p2 not in p1:
            return False

    cu = constraint.get("unit", "")
    qu = query.get("unit", "")
    if cu and qu and cu != qu:
        # mg/l и ppm считаем совместимыми
        if not ({cu, qu} <= {"mg/l", "ppm"}):
            return False

    cv = constraint.get("value")
    qv = query.get("value")
    qop = query.get("operator", "=")

    if constraint.get("operator") == "range":
        cmin, cmax = constraint.get("value_min"), constraint.get("value_max")
        if qv is not None and cmin is not None and cmax is not None:
            return cmin <= qv <= cmax
        return False

    if cv is None or qv is None:
        return query.get("parameter", "").lower() in str(constraint).lower()

    cop = constraint.get("operator", "=")
    # constraint говорит «≤300», query «<200» — ищем случаи где constraint допускает qv
    if qop == "<":
        return cv < qv or (cop in ("<=", "<") and cv <= qv)
    if qop == "<=":
        return cv <= qv or (cop in ("<=", "<") and cv <= qv)
    if qop == ">":
        return cv > qv or (cop in (">=", ">") and cv >= qv)
    if qop == ">=":
        return cv >= qv or (cop in (">=", ">") and cv >= qv)
    return abs(cv - qv) < max(0.01 * qv, 1.0)
