"""API-роутер: экспорт отчётов (md, pdf, jsonld)."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api.auth import audit_action, check_permission, get_current_user
from services.export_service import export_jsonld, export_markdown, export_pdf, save_export

router = APIRouter(prefix="/api/v1", tags=["platform"])


class ExportRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    format: str = Field(..., pattern="^(md|pdf|jsonld)$")
    download: bool = Field(default=False, description="Вернуть файл для скачивания вместо JSON")


def _safe_filename(topic: str, ext: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in topic).strip()[:50]
    return f"{safe or 'report'}.{ext}"


def _content_disposition(filename: str) -> str:
    """ASCII fallback + RFC 5987 UTF-8 для кириллицы в имени файла."""
    ascii_name = "".join(c if ord(c) < 128 and c not in ('"', "\\") else "_" for c in filename)
    if not ascii_name.strip("._"):
        ascii_name = "report" + (filename[filename.rfind("."):] if "." in filename else ".bin")
    utf8_name = quote(filename, safe="")
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{utf8_name}'


def _file_response(topic: str, fmt: str) -> Response:
    ext = "jsonld" if fmt == "jsonld" else fmt
    filename = _safe_filename(topic, ext)
    disposition = _content_disposition(filename)
    if fmt == "pdf":
        content = export_pdf(topic)
        return Response(content, media_type="application/pdf", headers={"Content-Disposition": disposition})
    if fmt == "jsonld":
        return Response(
            export_jsonld(topic),
            media_type="application/ld+json",
            headers={"Content-Disposition": disposition},
        )
    return Response(
        export_markdown(topic),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": disposition},
    )


@router.post("/export")
async def export_report(body: ExportRequest, user=Depends(get_current_user)):
    check_permission(user, "export")
    audit_action(user, "export", body.format, {"topic": body.topic})
    if body.download:
        return _file_response(body.topic, body.format)
    path = save_export(body.topic, body.format)
    if body.format == "md":
        return {"format": "md", "content": export_markdown(body.topic), "path": str(path)}
    if body.format == "jsonld":
        return {"format": "jsonld", "content": export_jsonld(body.topic), "path": str(path)}
    return {"format": "pdf", "path": str(path), "size_bytes": path.stat().st_size}


@router.get("/export/{topic}/download")
async def download_export(topic: str, format: str = "md", user=Depends(get_current_user)):
    check_permission(user, "export")
    ext = "jsonld" if format == "jsonld" else format
    disposition = _content_disposition(_safe_filename(topic, ext))
    if format == "pdf":
        content = export_pdf(topic)
        return Response(content, media_type="application/pdf", headers={"Content-Disposition": disposition})
    if format == "jsonld":
        return Response(export_jsonld(topic), media_type="application/ld+json", headers={"Content-Disposition": disposition})
    return Response(export_markdown(topic), media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": disposition})
