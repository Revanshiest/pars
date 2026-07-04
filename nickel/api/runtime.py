"""Общие рантайм-объекты API: хранилище задач, агент поиска, фоновый пайплайн.

Вынесено из api/main.py, чтобы доменные роутеры (ingest, jobs, search)
и стартовая логика приложения делили один и тот же JobStore/агент/executor.
"""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from api.jobs import JobStore
from agent.yandex_agent import YandexKnowledgeAgent
from services.pipeline_runner import run_full_pipeline

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "data/uploads")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "data/outputs")

job_store = JobStore()
search_agent = YandexKnowledgeAgent()
_pipeline_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pipeline")


def _run_pipeline_in_thread(
    filepath: str,
    job_id: str,
    extractor_backend: str | None,
    on_progress,
) -> dict:
    """Тяжёлый пайплайн в отдельном потоке — не блокирует HTTP."""
    return asyncio.run(
        run_full_pipeline(
            filepath,
            job_id,
            llm_extractor=None,
            on_progress=on_progress,
            output_dir=OUTPUT_DIR,
            extractor_backend=extractor_backend or os.getenv("EXTRACTOR_BACKEND"),
        )
    )


async def _run_job(job_id: str, filepath: str, extractor_backend: str | None = None):
    def on_progress(stage, current, total, message=None):
        job_store.update_progress(job_id, stage, current, total, message)

    loop = asyncio.get_running_loop()
    try:
        job_store.update_progress(job_id, "starting", 0, 1, "Запуск пайплайна")
        result = await loop.run_in_executor(
            _pipeline_executor,
            _run_pipeline_in_thread,
            filepath,
            job_id,
            extractor_backend,
            on_progress,
        )
        job_store.complete_job(job_id, result)
    except Exception as e:
        job_store.fail_job(job_id, str(e))


async def _run_batch_job(
    batch_id: str,
    folder: Path,
    extractor_backend: str | None,
    recursive: bool,
):
    from services.folder_ingest import scan_folder

    files = scan_folder(folder, recursive=recursive)
    total = len(files)
    job_store.update_progress(batch_id, "scan", 0, max(total, 1), f"Найдено файлов: {total}")
    job_store.update_batch_stats(batch_id, 0, 0, total)

    if total == 0:
        job_store.complete_job(batch_id, {"files_processed": 0, "folder": str(folder)})
        return

    done, failed = 0, 0
    child_results = []
    for idx, filepath in enumerate(files, start=1):
        child_id = job_store.create_job(
            filepath.name,
            str(filepath),
            job_type="single",
            batch_id=batch_id,
            created_by=job_store.get_job(batch_id).get("created_by"),
        )
        job_store.append_log(
            batch_id,
            f"[{idx}/{total}] Старт: {filepath.name}",
            stage="batch",
        )

        def on_progress(stage, current, progress_total, message=None, _cid=child_id):
            job_store.update_progress(_cid, stage, current, progress_total, message)

        try:
            job_store.update_progress(child_id, "starting", 0, 1, "Запуск пайплайна")
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                _pipeline_executor,
                _run_pipeline_in_thread,
                str(filepath),
                child_id,
                extractor_backend,
                on_progress,
            )
            job_store.complete_job(child_id, result)
            done += 1
            child_results.append({"file": filepath.name, "status": "completed", "job_id": child_id})
            job_store.append_log(batch_id, f"✓ {filepath.name}", stage="batch", level="success")
        except Exception as e:
            job_store.fail_job(child_id, str(e))
            failed += 1
            child_results.append({"file": filepath.name, "status": "failed", "error": str(e), "job_id": child_id})
            job_store.append_log(batch_id, f"✗ {filepath.name}: {e}", stage="batch", level="error")

        job_store.update_batch_stats(batch_id, done, failed, total)
        job_store.update_progress(
            batch_id,
            "batch",
            done + failed,
            total,
            f"Обработано {done + failed}/{total} (ошибок: {failed})",
        )

    summary = {
        "folder": str(folder),
        "files_total": total,
        "files_done": done,
        "files_failed": failed,
        "children": child_results,
    }
    if failed == total:
        job_store.fail_job(batch_id, f"Все {total} файлов завершились с ошибкой")
    elif failed > 0:
        job_store.complete_job(batch_id, summary)
        job_store.append_log(
            batch_id,
            f"Пакет завершён с ошибками: {failed}/{total}",
            level="warning",
        )
    else:
        job_store.complete_job(batch_id, summary)
