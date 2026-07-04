"""Сопоставление документов с JSON-тройками для импорта пар."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from services.folder_ingest import _file_size

DOC_EXTENSIONS = {".pdf", ".md", ".txt", ".docx", ".xlsx", ".xls"}
JSON_EXTENSION = ".json"


JSON_STEM_SUFFIXES = ("_extracted", "_yandex_graph")


def json_pair_stem(path: Path) -> str:
    """report_extracted.json / report_yandex_graph.json → report."""
    stem = path.stem
    for suffix in JSON_STEM_SUFFIXES:
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def scan_doc_json_pairs(folder: Path, recursive: bool = False) -> List[Tuple[Path, Path]]:
    """Найти пары (документ, json) в папке по общему stem."""
    docs: dict[str, Path] = {}
    jsons: dict[str, Path] = {}

    paths: List[Path] = []
    if recursive:
        paths = [p for p in folder.rglob("*") if p.is_file()]
    else:
        paths = [p for p in folder.iterdir() if p.is_file()]

    for path in sorted(paths):
        suffix = path.suffix.lower()
        if suffix in DOC_EXTENSIONS:
            docs[path.stem] = path
        elif suffix == JSON_EXTENSION:
            jsons[json_pair_stem(path)] = path

    pairs: List[Tuple[Path, Path]] = []
    for stem, doc_path in sorted(docs.items()):
        if stem in jsons:
            pairs.append((doc_path, jsons[stem]))
    pairs.sort(key=lambda p: (_file_size(p[0]), p[0].name.lower()))
    return pairs


def pair_uploaded_files(filenames_and_paths: List[Tuple[str, str]]) -> List[Tuple[str, str, str, str]]:
    """
    Сопоставить загруженные файлы по имени.
    Возвращает списки (doc_name, doc_path, json_name, json_path).
    """
    docs: dict[str, Tuple[str, str]] = {}
    jsons: dict[str, Tuple[str, str]] = {}

    for name, path in filenames_and_paths:
        p = Path(name)
        suffix = p.suffix.lower()
        if suffix in DOC_EXTENSIONS:
            docs[p.stem] = (name, path)
        elif suffix == JSON_EXTENSION:
            jsons[json_pair_stem(p)] = (name, path)

    pairs: List[Tuple[str, str, str, str]] = []
    for stem in sorted(docs.keys()):
        if stem in jsons:
            doc_name, doc_path = docs[stem]
            json_name, json_path = jsons[stem]
            pairs.append((doc_name, doc_path, json_name, json_path))
    return pairs
