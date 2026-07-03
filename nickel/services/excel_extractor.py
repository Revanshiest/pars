"""Извлечение троек из Excel — обёртка над excel_mapper для API."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

import pandas as pd

from excel_mapper import ExcelSmartMapper
from ontology.schema import filter_valid_triples


async def extract_triples_from_excel(filepath: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    mapper = ExcelSmartMapper()
    all_triples: List[Dict[str, Any]] = []
    sheets_processed = []

    xls = pd.ExcelFile(filepath)
    for sheet_name in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet_name)
        if df.empty or len(df.columns) < 2:
            continue
        rules = await mapper.generate_schema(os.path.basename(filepath), sheet_name, df)
        if not rules:
            continue
        sheet_triples = mapper.apply_schema(df, rules)
        for t in sheet_triples:
            t.setdefault("properties", {})["sheet"] = sheet_name
            t["properties"]["source_type"] = "experiment_catalog"
            t["source_chunk"] = f"excel:{sheet_name}"
        all_triples.extend(sheet_triples)
        sheets_processed.append({"sheet": sheet_name, "rows": len(df), "triples": len(sheet_triples)})

    valid = filter_valid_triples(all_triples)
    metadata = {
        "source_file": os.path.basename(filepath),
        "literature_type": "Excel",
        "sheets": sheets_processed,
        "document_kind": "experiment_catalog",
    }
    return valid, metadata
