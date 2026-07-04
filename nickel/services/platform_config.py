"""Загрузка конфигурации платформы из nickel/config/*.json."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load_json(name: str) -> Dict[str, Any]:
    path = CONFIG_DIR / name
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def domains_config() -> Dict[str, Any]:
    return _load_json("domains.json")


@lru_cache(maxsize=1)
def verification_policy() -> Dict[str, Any]:
    data = _load_json("verification_policy.json")
    return data or {
        "default_confidence": 0.7,
        "manual_edit_confidence": 0.9,
        "json_import_confidence": 0.85,
        "verified_boost": 0.15,
        "doi_boost": 0.05,
        "page_boost": 0.03,
        "internal_unverified_penalty": 0.05,
        "expert_min_confidence": 0.7,
        "tiers": {"high": 0.85, "medium": 0.65, "medium_unverified_confidence": 0.75, "low": 0.5},
    }


@lru_cache(maxsize=1)
def platform_defaults() -> Dict[str, Any]:
    return _load_json("platform_defaults.json")


def domain_processes() -> Dict[str, List[str]]:
    """Домен → список ключевых процессов (из config/domains.json)."""
    cfg = domains_config()
    out: Dict[str, List[str]] = {}
    for key, meta in (cfg.get("domains") or {}).items():
        out[key] = list(meta.get("processes") or [])
    return out


def gap_analysis_settings() -> Dict[str, Any]:
    return domains_config().get("gap_analysis") or {}


def search_examples() -> List[str]:
    return list(domains_config().get("search_examples") or [])


def glossary_similarity_threshold() -> float:
    defaults = platform_defaults()
    env = os.getenv("GLOSSARY_SIM_THRESHOLD")
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    return float((defaults.get("glossary") or {}).get("similarity_threshold", 0.72))


def fair_defaults() -> Dict[str, str]:
    base = (platform_defaults().get("fair") or {}).copy()
    base["ontology"] = os.getenv("FAIR_ONTOLOGY", base.get("ontology", "nickel-kg-v1"))
    base["license"] = os.getenv("FAIR_LICENSE", base.get("license", "internal-rd-use"))
    base["provenance"] = os.getenv("FAIR_PROVENANCE", base.get("provenance", "llm_extraction_pipeline"))
    return base


def compare_defaults() -> Dict[str, Any]:
    return platform_defaults().get("compare") or {}


def geography_markers() -> Dict[str, Any]:
    return platform_defaults().get("geography") or {}


def default_confidence() -> float:
    return float(verification_policy().get("default_confidence", 0.7))
