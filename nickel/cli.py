#!/usr/bin/env python3
"""Единая точка входа Nickel: API, пайплайн, экспорт, health."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# nickel/ на PYTHONPATH
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv

load_dotenv()


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        app_dir=str(_ROOT),
    )
    return 0


def cmd_pipeline(args: argparse.Namespace) -> int:
    from services.pipeline_runner import run_full_pipeline

    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 1

    def on_progress(stage, current, total, message=None):
        pct = int(100 * current / total) if total else 0
        msg = message or stage
        print(f"[{stage}] {pct}% — {msg}")

    result = asyncio.run(
        run_full_pipeline(
            str(path),
            job_id=args.job_id or path.stem,
            on_progress=on_progress,
            output_dir=args.output_dir,
            extractor_backend=args.extractor,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    from services.export_service import export_jsonld, export_markdown, export_pdf, save_export

    if args.out:
        path = save_export(args.topic, args.format, output_dir=str(Path(args.out).parent))
        print(path)
        return 0

    if args.format == "md":
        print(export_markdown(args.topic))
    elif args.format == "jsonld":
        print(export_jsonld(args.topic))
    elif args.format == "pdf":
        data = export_pdf(args.topic)
        out = Path(args.output_dir) / f"{args.topic[:50]}.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        print(out)
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    from services.health import check_health, check_liveness, check_readiness

    if args.kind == "live":
        print(json.dumps(check_liveness(), indent=2))
        return 0
    if args.kind == "ready":
        report = check_readiness()
    else:
        report = check_health(include_ollama=not args.no_ollama)

    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    if report.status == "unavailable":
        return 2
    if report.status == "degraded":
        return 1
    return 0


def cmd_mvp(args: argparse.Namespace) -> int:
    """Legacy: pipeline_mvp без Neo4j/Qdrant (только LLM extraction)."""
    from pipeline_mvp import run_pipeline

    asyncio.run(run_pipeline(args.file))
    return 0


def cmd_visualize(args: argparse.Namespace) -> int:
    from services.html_visualizer import generate_html

    out_dir = str(Path(args.output).parent)
    generate_html(args.input, out_dir)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nickel",
        description="Nickel R&D Knowledge Graph — CLI",
    )
    sub = p.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Запуск FastAPI (uvicorn)")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(func=cmd_serve)

    pipe = sub.add_parser("pipeline", help="Полный пайплайн: ingest → extract → Neo4j/Qdrant")
    pipe.add_argument("file", help="PDF/DOCX/MD/XLSX")
    pipe.add_argument("--job-id", default=None)
    pipe.add_argument("--extractor", default=os.getenv("EXTRACTOR_BACKEND", "auto"))
    pipe.add_argument("--output-dir", default=os.getenv("OUTPUT_DIR", "data/outputs"))
    pipe.set_defaults(func=cmd_pipeline)

    exp = sub.add_parser("export", help="Экспорт lit review (md/jsonld/pdf)")
    exp.add_argument("--topic", required=True)
    exp.add_argument("--format", choices=["md", "jsonld", "pdf"], default="md")
    exp.add_argument("--out", help="Путь к файлу")
    exp.add_argument("--output-dir", default=os.getenv("OUTPUT_DIR", "data/exports"))
    exp.set_defaults(func=cmd_export)

    hlth = sub.add_parser("health", help="Проверка компонентов")
    hlth.add_argument("--kind", choices=["health", "ready", "live"], default="health")
    hlth.add_argument("--no-ollama", action="store_true")
    hlth.set_defaults(func=cmd_health)

    mvp = sub.add_parser("mvp", help="Legacy MVP extraction (без graph store)")
    mvp.add_argument("file")
    mvp.set_defaults(func=cmd_mvp)

    viz = sub.add_parser("visualize", help="HTML-граф из JSON triplet")
    viz.add_argument("input")
    viz.add_argument("-o", "--output", default="graph.html")
    viz.set_defaults(func=cmd_visualize)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
