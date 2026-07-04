"""Оркестрация пайплайна: DOCX, Excel, Yandex/Ollama, entity resolution, Neo4j, Qdrant."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from ontology.schema import filter_valid_triples
from services.document_types import detect_document_kind, enrich_triples_with_document_context
from services.entity_resolution import resolve_entities
from services.excel_extractor import extract_triples_from_excel
from services.extractors import get_text_extractor
from services.glossary import normalize_triples
from services.json_ingest import import_glossary_json, load_triples_json, parse_json_upload
from services.neo4j_loader import Neo4jLoader
from services.qdrant_index import QdrantIndexer
from services.rdf_export import export_json_to_rdf, triples_to_graph, validate_shacl
from services.store import get_store

ProgressCallback = Callable[[str, int, int, Optional[str]], None]

EXCEL_EXTENSIONS = {".xlsx", ".xls"}
TEXT_EXTENSIONS = {".pdf", ".md", ".txt", ".docx"}
JSON_EXTENSION = ".json"


async def _read_document(filepath: str) -> str:
    lower = filepath.lower()
    if lower.endswith(".pdf"):
        import pymupdf4llm
        return pymupdf4llm.to_markdown(filepath, write_images=False)
    if lower.endswith(".docx"):
        from docx import Document
        doc = Document(filepath)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    with open(filepath, encoding="utf-8") as f:
        return f.read()


def _chunk_document(markdown_document: str, filepath: str) -> List[Dict[str, Any]]:
    headers_to_split_on = [("#", "Header 1"), ("##", "Header 2"), ("###", "Header 3")]
    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    md_header_splits = markdown_splitter.split_text(markdown_document)

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    splits = text_splitter.split_documents(md_header_splits)

    doc_kind = detect_document_kind(filepath, markdown_document)
    chunks = []
    for idx, doc in enumerate(splits):
        headers = " > ".join(v for k, v in doc.metadata.items() if k.startswith("Header"))
        chunks.append({
            "id": f"chunk_{idx}",
            "text": doc.page_content,
            "headers": headers,
            "meta_context": (
                f"Файл: {os.path.basename(filepath)} | "
                f"Тип: {doc_kind['label']} | Раздел: {headers}"
            ),
        })
    return chunks


async def _extract_from_text_document(
    filepath: str,
    extractor,
    on_progress: Optional[ProgressCallback],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], str]:
    markdown = await _read_document(filepath)
    chunks = _chunk_document(markdown, filepath)

    if on_progress:
        on_progress("ingest", 1, 1, f"Разбито на {len(chunks)} чанков")

    from orchestrator import should_process_chunk

    all_triples: List[Dict[str, Any]] = []
    batch_size = 3 if type(extractor).__name__ == "OllamaExtractorAdapter" else 8
    total_batches = (len(chunks) - 1) // batch_size + 1 if chunks else 0

    for i in range(0, len(chunks), batch_size):
        batch = [c for c in chunks[i : i + batch_size] if should_process_chunk(c["text"])]
        if not batch:
            continue
        batch_num = i // batch_size + 1
        if on_progress:
            on_progress("extract", batch_num, total_batches, f"Батч {batch_num}/{total_batches}")

        tasks = [extractor.extract_triples(c["text"], c["meta_context"]) for c in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for chunk, res in zip(batch, results):
            if isinstance(res, list):
                from services.document_metadata import page_from_chunk
                page = page_from_chunk(chunk)
                if page is not None:
                    chunk["page"] = page
                for t in res:
                    t.setdefault("source_chunk", chunk["id"])
                    if page is not None:
                        t["source_page"] = page
                        t.setdefault("properties", {})["source_page"] = page
                all_triples.extend(res)
            elif isinstance(res, Exception):
                continue

    return all_triples, chunks, markdown


async def run_full_pipeline(
    filepath: str,
    job_id: str,
    llm_extractor=None,
    on_progress: Optional[ProgressCallback] = None,
    output_dir: str = "data/outputs",
    extractor_backend: Optional[str] = None,
) -> Dict[str, Any]:
    """Полный цикл с поддержкой PDF/DOCX/Excel и Yandex/Ollama."""

    def progress(stage: str, current: int, total: int, message: Optional[str] = None):
        if on_progress:
            on_progress(stage, current, total, message)

    os.makedirs(output_dir, exist_ok=True)
    basename = Path(filepath).stem
    suffix = Path(filepath).suffix.lower()
    store = get_store()

    progress("route", 0, 1, f"Определение типа файла: {suffix}")
    doc_kind = detect_document_kind(filepath)
    chunks: List[Dict[str, Any]] = []
    markdown = ""

    if suffix in EXCEL_EXTENSIONS:
        progress("extract", 0, 1, "Извлечение из Excel (Smart Mapper)")
        triple_dicts, excel_meta = await extract_triples_from_excel(filepath)
        extraction_backend = "excel_mapper"
        document_metadata = excel_meta
    elif suffix == JSON_EXTENSION:
        progress("ingest", 0, 1, "Чтение JSON")
        kind, payload = parse_json_upload(filepath)
        if kind == "glossary":
            glossary_import = import_glossary_json(payload)
            progress(
                "glossary",
                1,
                1,
                f"Импорт глоссария: +{glossary_import['terms_added']} терминов",
            )
            progress("done", 1, 1, "Готово")
            return {
                "job_id": job_id,
                "document_kind": {"kind": "glossary", "label": "Глоссарий"},
                "extraction_backend": "json_glossary",
                "triples_count": 0,
                "chunks_count": 0,
                "entity_resolution": {},
                "numeric_extraction": {},
                "glossary": glossary_import,
                "glossary_import": glossary_import,
                "document_metadata": {"source_file": os.path.basename(filepath)},
            }
        triple_dicts, document_metadata = load_triples_json(payload)
        progress("import", 0, 1, "Быстрый импорт JSON (без BGE)")
        from services.json_graph_import import import_triples_json_file

        result = import_triples_json_file(filepath, job_id)
        progress("done", 1, 1, f"Импортировано {result.get('triples_count', 0)} triples")
        return result
    else:
        if suffix not in TEXT_EXTENSIONS:
            raise ValueError(f"Unsupported format: {suffix}")

        extractor = llm_extractor or get_text_extractor(extractor_backend)
        extraction_backend = extractor_backend or os.getenv("EXTRACTOR_BACKEND", "auto")
        if type(extractor).__name__ == "YandexExtractorAdapter":
            extraction_backend = "yandex"
        elif type(extractor).__name__ == "OllamaExtractorAdapter":
            extraction_backend = "ollama"

        progress("ingest", 0, 1, "Чтение документа")
        triple_dicts, chunks, markdown = await _extract_from_text_document(
            filepath, extractor, on_progress
        )
        document_metadata = {
            "source_file": os.path.basename(filepath),
            "document_kind": doc_kind["kind"],
            "label": doc_kind["label"],
        }

    triple_dicts = filter_valid_triples(triple_dicts)

    progress("document_context", 0, 1, "Обогащение патентов/нормативов")
    triple_dicts = enrich_triples_with_document_context(
        triple_dicts, filepath, markdown or json.dumps(document_metadata)
    )

    progress("entity_resolution", 0, 1, "Entity resolution (post_processor)")
    triple_dicts, er_stats = await resolve_entities(triple_dicts)

    progress("numeric_extract", 0, 1, "Извлечение числовых параметров (regex+validator)")
    from services.numeric_parser import enrich_triples_with_numerics
    triple_dicts, numeric_stats = enrich_triples_with_numerics(triple_dicts, markdown or os.path.basename(filepath))

    from services.document_metadata import enrich_document_metadata
    from services.glossary import detect_geography

    geo = detect_geography(markdown or os.path.basename(filepath))
    document_metadata = enrich_document_metadata(
        document_metadata, markdown or os.path.basename(filepath), doc_kind, geography=geo
    )
    for t in triple_dicts:
        props = t.setdefault("properties", {})
        if document_metadata.get("year"):
            props.setdefault("year", document_metadata["year"])
        if document_metadata.get("author"):
            props.setdefault("author", document_metadata["author"])
        props.setdefault("document_kind", document_metadata.get("document_kind", doc_kind.get("kind")))

    progress("glossary", 0, 1, "Нормализация через глоссарий (BGE)")
    triple_dicts, glossary_stats = normalize_triples(
        triple_dicts, document_text=markdown or os.path.basename(filepath)
    )

    doi = None
    from services.fair_metadata import attach_provenance, build_fair_metadata, extract_doi
    if markdown:
        doi = extract_doi(markdown)
    fair = build_fair_metadata(
        source_document=basename,
        job_id=job_id,
        document_kind=doc_kind.get("kind", "report"),
        doi=doi,
        source_file_path=os.path.basename(filepath),
    )
    document_metadata["fair"] = fair
    document_metadata["doi"] = doi
    triple_dicts = attach_provenance(
        triple_dicts,
        source_document=basename,
        job_id=job_id,
        fair=fair,
        chunks=chunks,
    )

    store.register_document(
        job_id,
        basename,
        document_kind=document_metadata.get("document_kind"),
        author=document_metadata.get("author"),
        year=document_metadata.get("year"),
        geography=document_metadata.get("geography") or geo,
        doi=doi,
        metadata=document_metadata,
    )

    progress("validate", 0, 1, "SHACL-валидация")
    graph = triples_to_graph(triple_dicts, source_document=basename)
    shacl_result = validate_shacl(graph)
    shacl_valid = shacl_result.get("valid", True)
    strict_shacl = os.getenv("STRICT_SHACL", "true").lower() == "true"

    store.upsert_facts(
        triple_dicts, job_id=job_id, source_document=basename, shacl_valid=shacl_valid
    )

    json_path = os.path.join(output_dir, f"{basename}_{job_id}_extracted.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "document_metadata": document_metadata,
            "triples": triple_dicts,
            "shacl": shacl_result,
        }, f, indent=2, ensure_ascii=False)

    progress("rdf", 0, 1, "Экспорт RDF")
    rdf_path = export_json_to_rdf(Path(json_path), Path(os.path.join(output_dir, f"{basename}_{job_id}.ttl")))

    neo4j_stats: Dict[str, Any] = {"relationships_loaded": 0}
    if strict_shacl and not shacl_valid:
        progress("neo4j", 0, 1, "Пропуск Neo4j: SHACL validation failed")
        neo4j_stats = {
            "skipped": True,
            "reason": "SHACL validation failed",
            "report": shacl_result.get("report", "")[:500],
        }
    else:
        progress("neo4j", 0, 1, "Загрузка в Neo4j")
        try:
            verified_triples = [
                t for t in triple_dicts
                if t.get("verification_status") != "rejected"
            ]
            with Neo4jLoader() as loader:
                loader.init_schema()
                neo4j_stats = loader.load_triples(
                    verified_triples, job_id=job_id, source_document=basename
                )
        except Exception as e:
            neo4j_stats = {"error": str(e)}

    qdrant_stats: Dict[str, Any] = {"chunks": 0, "entities": 0}
    if os.getenv("INDEX_QDRANT_ON_IMPORT", "false").lower() in ("1", "true", "yes"):
        progress("qdrant", 0, 1, "Индексация в Qdrant")
        try:
            indexer = QdrantIndexer()
            chunk_meta = {
                "document_kind": document_metadata.get("document_kind"),
                "year": document_metadata.get("year"),
                "author": document_metadata.get("author"),
                "geography": document_metadata.get("geography"),
            }
            if chunks:
                qdrant_stats["chunks"] = indexer.index_chunks(
                    chunks, job_id, basename, metadata=chunk_meta
                )
            entities = {}
            for t in triple_dicts:
                entities[(t["subject"], t["subject_type"])] = {"name": t["subject"], "type": t["subject_type"]}
                entities[(t["object"], t["object_type"])] = {"name": t["object"], "type": t["object_type"]}
            qdrant_stats["entities"] = indexer.index_entities(
                list(entities.values()), job_id, metadata=chunk_meta
            )
        except Exception as e:
            qdrant_stats = {"error": str(e)}
    else:
        progress("qdrant", 1, 1, "Пропуск Qdrant (INDEX_QDRANT_ON_IMPORT=false)")
        qdrant_stats = {"skipped": True, "reason": "INDEX_QDRANT_ON_IMPORT=false"}

    progress("done", 1, 1, "Готово")
    keywords = list({t["subject"] for t in triple_dicts[:20]} | {t["object"] for t in triple_dicts[:20]})
    store.notify_subscribers(
        keywords,
        f"Новый документ: {basename}",
        f"Извлечено {len(triple_dicts)} фактов ({doc_kind['label']}). Job: {job_id}",
    )

    return {
        "job_id": job_id,
        "document_kind": doc_kind,
        "extraction_backend": extraction_backend,
        "triples_count": len(triple_dicts),
        "chunks_count": len(chunks),
        "entity_resolution": er_stats,
        "numeric_extraction": numeric_stats,
        "glossary": glossary_stats,
        "document_metadata": document_metadata,
        "json_path": json_path,
        "rdf_path": str(rdf_path),
        "shacl": shacl_result,
        "neo4j": neo4j_stats,
        "qdrant": qdrant_stats,
    }
