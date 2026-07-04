"""Глоссарий: exact match + BGE semantic synonym matching."""

from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from services.store import get_store

from services.platform_config import default_confidence, glossary_similarity_threshold
from services.geography import detect_geography as _detect_geography_impl

ProgressCallback = Callable[[int, int, Optional[str]], None]


def detect_geography(text: str, filepath: str = "", doc_kind: Optional[dict] = None) -> str | None:
    """Определяет geography документа (RU / EN / global)."""
    return _detect_geography_impl(text, filepath=filepath, doc_kind=doc_kind)


def glossary_use_bge() -> bool:
    return os.getenv("GLOSSARY_USE_BGE", "true").lower() in ("1", "true", "yes")


class GlossaryMatcher:
    """Exact index + BGE-m3 semantic similarity для синонимов RU/EN."""

    def __init__(self, use_bge: bool = True):
        self.use_bge = use_bge
        self._embedder = None
        self._term_vectors: Optional[np.ndarray] = None
        self._term_entries: List[Dict[str, Any]] = []

    @property
    def sim_threshold(self) -> float:
        return glossary_similarity_threshold()

    @property
    def embedder(self):
        if self._embedder is None:
            from langchain_community.embeddings import HuggingFaceEmbeddings
            self._embedder = HuggingFaceEmbeddings(model_name="BAAI/bge-m3")
        return self._embedder

    def _build_entries(self) -> List[Dict[str, Any]]:
        entries = []
        for term in get_store().iter_glossary():
            forms = [term["canonical"]] + term["synonyms_ru"] + term["synonyms_en"]
            for form in forms:
                entries.append({
                    "form": form,
                    "canonical": term["canonical"],
                    "domain": term.get("domain"),
                    "lang": "ru" if re.search(r"[а-яё]", form, re.I) else "en",
                })
        return entries

    def _ensure_vectors(self):
        if not self.use_bge:
            return
        entries = self._build_entries()
        if entries == self._term_entries and self._term_vectors is not None:
            return
        self._term_entries = entries
        if not entries:
            self._term_vectors = np.array([])
            return
        texts = [e["form"] for e in entries]
        self._term_vectors = np.array(self.embedder.embed_documents(texts))

    def semantic_lookup(self, text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """BGE: найти ближайшие термины глоссария к фрагменту текста."""
        if not self.use_bge:
            return []
        self._ensure_vectors()
        if self._term_vectors is None or len(self._term_vectors) == 0:
            return []

        q_vec = np.array(self.embedder.embed_query(text))
        norms = np.linalg.norm(self._term_vectors, axis=1) * np.linalg.norm(q_vec)
        norms = np.where(norms == 0, 1, norms)
        scores = self._term_vectors @ q_vec / norms

        top_idx = np.argsort(scores)[::-1][:top_k * 2]
        seen_canonical = set()
        results = []
        for idx in top_idx:
            score = float(scores[idx])
            if score < self.sim_threshold:
                break
            entry = self._term_entries[idx]
            if entry["canonical"] in seen_canonical:
                continue
            seen_canonical.add(entry["canonical"])
            results.append({
                "canonical": entry["canonical"],
                "matched_form": entry["form"],
                "score": round(score, 3),
                "lang": entry["lang"],
            })
            if len(results) >= top_k:
                break
        return results

    def normalize_term(self, name: str, index: Optional[Dict[str, str]] = None) -> Tuple[str, Optional[Dict]]:
        index = index or get_store().build_glossary_index()
        key = name.strip().lower()
        if key in index:
            return index[key], None
        if self.use_bge:
            matches = self.semantic_lookup(name, top_k=1)
            if matches:
                return matches[0]["canonical"], matches[0]
        return name.strip(), None


@lru_cache(maxsize=1)
def _matcher(use_bge: bool = True) -> GlossaryMatcher:
    return GlossaryMatcher(use_bge=use_bge)


def normalize_entity(name: str, index: Optional[Dict[str, str]] = None) -> str:
    index = index or get_store().build_glossary_index()
    key = name.strip().lower()
    if key in index:
        return index[key]
    canonical, _ = _matcher(glossary_use_bge()).normalize_term(name, index=index)
    return canonical


def normalize_triples(
    triples: List[Dict[str, Any]],
    document_text: str = "",
    auto_learn: bool = True,
    use_bge: Optional[bool] = None,
    on_progress: Optional[ProgressCallback] = None,
    document_geography: Optional[str] = None,
    document_kind: Optional[dict] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    store = get_store()
    use_bge = glossary_use_bge() if use_bge is None else use_bge
    matcher = _matcher(use_bge)
    index = store.build_glossary_index()
    geo = document_geography or detect_geography(
        document_text, doc_kind=document_kind
    )
    default_conf = default_confidence()
    stats = {"normalized": 0, "semantic_normalized": 0, "new_terms": 0}
    term_cache: Dict[str, Tuple[str, Optional[Dict]]] = {}
    pending_terms: List[Dict[str, Any]] = []
    total = len(triples)

    if use_bge and total > 0 and on_progress:
        on_progress(0, total, "Загрузка BGE-m3 (первый запуск может занять несколько минут)")

    for i, t in enumerate(triples):
        for field in ("subject", "object"):
            orig = t[field]
            key = orig.strip().lower()
            if key not in term_cache:
                term_cache[key] = matcher.normalize_term(orig, index=index)
            canonical, match = term_cache[key]
            t[field] = canonical
            if canonical != orig:
                stats["normalized"] += 1
                if match:
                    stats["semantic_normalized"] += 1

        if not t.get("geography"):
            t["geography"] = geo
        if t.get("confidence") is None:
            t["confidence"] = default_conf
        t.setdefault("verification_status", "pending")

        if auto_learn:
            for name, etype in [(t["subject"], t["subject_type"]), (t["object"], t["object_type"])]:
                nkey = name.lower()
                if nkey not in index and len(name) > 2:
                    pending_terms.append({
                        "canonical": name,
                        "synonyms_ru": [],
                        "synonyms_en": [],
                        "domain": etype,
                        "definition": "Автоматически извлечено из документа",
                    })
                    index[nkey] = name
                    stats["new_terms"] += 1

        if on_progress and (i == 0 or (i + 1) % 50 == 0 or i + 1 == total):
            on_progress(i + 1, total, f"Нормализация тройки {i + 1}/{total}")

    for term in pending_terms:
        store.add_glossary_term(term, source="pipeline")

    if pending_terms:
        matcher._term_vectors = None
        matcher._term_entries = []

    return triples, stats


def text_glossary_lookup(text: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Быстрый текстовый поиск по глоссарию (без BGE)."""
    needle = text.strip().lower()
    if len(needle) < 2:
        return []
    results: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for term in get_store().list_glossary(q=text, limit=100):
        forms = [term["canonical"]] + term["synonyms_ru"] + term["synonyms_en"]
        best_form = None
        best_score = 0.0
        for form in forms:
            fl = form.lower()
            if fl == needle:
                score = 1.0
            elif needle in fl or fl in needle:
                score = 0.85
            elif any(part in fl for part in needle.split() if len(part) > 2):
                score = 0.75
            else:
                continue
            if score > best_score:
                best_score = score
                best_form = form
        if best_form and term["canonical"] not in seen:
            seen.add(term["canonical"])
            results.append({
                "canonical": term["canonical"],
                "matched_form": best_form,
                "score": round(best_score, 3),
                "lang": "ru" if re.search(r"[а-яё]", best_form, re.I) else "en",
            })
        if len(results) >= top_k:
            break
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def expand_query_with_glossary(query: str, use_bge: bool = True) -> Dict[str, Any]:
    """Exact + BGE расширение запроса синонимами RU/EN."""
    store = get_store()
    index = store.build_glossary_index()
    q_lower = query.lower()
    extras: List[str] = []
    matched_terms: List[Dict] = []

    for term in store.list_glossary(q=query, limit=50):
        all_forms = [term["canonical"]] + term["synonyms_ru"] + term["synonyms_en"]
        if any(f.lower() in q_lower for f in all_forms):
            matched_terms.append({"canonical": term["canonical"], "method": "exact"})
            extras.extend(all_forms[:4])

    if use_bge and glossary_use_bge():
        try:
            for hit in _matcher(True).semantic_lookup(query, top_k=5):
                matched_terms.append({**hit, "method": "bge"})
                extras.append(hit["canonical"])
                term = next(
                    (t for t in store.list_glossary(q=hit["canonical"], limit=5) if t["canonical"] == hit["canonical"]),
                    None,
                )
                if term:
                    extras.extend(term["synonyms_ru"][:2])
                    extras.extend(term["synonyms_en"][:2])
        except Exception:
            for hit in text_glossary_lookup(query, top_k=5):
                matched_terms.append({**hit, "method": "text"})
                extras.append(hit["canonical"])
    else:
        for hit in text_glossary_lookup(query, top_k=5):
            matched_terms.append({**hit, "method": "text"})
            extras.append(hit["canonical"])

    canonical = index.get(q_lower)
    if canonical:
        term = next(
            (t for t in store.list_glossary(q=canonical, limit=5) if t["canonical"] == canonical),
            None,
        )
        if term:
            extras.extend(term["synonyms_ru"] + term["synonyms_en"])

    unique_extras = list(dict.fromkeys(extras))
    expanded = query + (" " + " ".join(unique_extras) if unique_extras else "")

    return {
        "original": query,
        "expanded": expanded.strip(),
        "synonyms_added": unique_extras,
        "matched_terms": matched_terms,
    }
