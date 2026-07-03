"""Пакетная обработка документов из папки на сервере."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Tuple

ALLOWED_EXTENSIONS = {".pdf", ".md", ".txt", ".docx", ".xlsx", ".xls"}


def ingest_roots() -> List[Path]:
    raw = os.getenv("INGEST_ROOTS", "data/inbox,data/uploads")
    roots = []
    for part in raw.split(","):
        p = Path(part.strip()).resolve()
        p.mkdir(parents=True, exist_ok=True)
        roots.append(p)
    return roots


def resolve_folder_path(folder_path: str) -> Path:
    """Путь должен лежать внутри одного из INGEST_ROOTS."""
    raw = folder_path.strip()
    candidate = Path(raw).expanduser()
    roots = ingest_roots()
    data_base = Path(os.getenv("UPLOAD_DIR", "data/uploads")).resolve().parent

    candidates: List[Path] = []
    if candidate.is_absolute():
        candidates.append(candidate.resolve())
    else:
        for root in roots:
            candidates.append((root / raw).resolve())
            candidates.append((root / candidate).resolve())
        candidates.append((Path.cwd() / candidate).resolve())
        candidates.append((data_base / candidate).resolve())

    seen = set()
    for resolved in candidates:
        if resolved in seen or not resolved.is_dir():
            continue
        seen.add(resolved)
        for root in roots:
            if resolved == root:
                return resolved
            try:
                resolved.relative_to(root)
                return resolved
            except ValueError:
                continue

    allowed = ", ".join(str(r) for r in roots)
    raise ValueError(f"Path must be an existing directory under: {allowed}")


def list_ingest_folders() -> List[dict]:
    items = []
    for root in ingest_roots():
        items.append({"path": str(root), "name": root.name, "root": True})
        try:
            for child in sorted(root.iterdir()):
                if child.is_dir() and not child.name.startswith("."):
                    items.append({"path": str(child), "name": child.name, "root": False})
        except OSError:
            pass
    return items


def scan_folder(folder: Path, recursive: bool = False) -> List[Path]:
    files: List[Path] = []
    if recursive:
        for p in folder.rglob("*"):
            if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS:
                files.append(p)
    else:
        for p in sorted(folder.iterdir()):
            if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS:
                files.append(p)
    return files


def folder_stats(folder: Path, recursive: bool = False) -> Tuple[int, List[str]]:
    files = scan_folder(folder, recursive=recursive)
    return len(files), [f.name for f in files]
