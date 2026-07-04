"""API-роутер: экспорт отчётов (md, pdf, jsonld)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api.auth import audit_action, check_permission, get_current_user
from services.export_service import export_jsonld, export_markdown, export_pdf, save_export

router = APIRouter(prefix="/api/v1", tags=["platform"])


class ExportRequest(BaseModel):
    topic: str
    format: str = Field(..., pattern="^(md|pdf|jsonld)$")


@router.post("/export")
async def export_report(body: ExportRequest, user=Depends(get_current_user)):
    check_permission(user, "export")
    audit_action(user, "export", body.format, {"topic": body.topic})
    path = save_export(body.topic, body.format)
    if body.format == "md":
        return {"format": "md", "content": export_markdown(body.topic), "path": str(path)}
    if body.format == "jsonld":
        return {"format": "jsonld", "content": export_jsonld(body.topic), "path": str(path)}
    return {"format": "pdf", "path": str(path), "size_bytes": path.stat().st_size}


@router.get("/export/{topic}/download")
async def download_export(topic: str, format: str = "md", user=Depends(get_current_user)):
    check_permission(user, "export")
    if format == "pdf":
        content = export_pdf(topic)
        return Response(content, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{topic}.pdf"'})
    if format == "jsonld":
        return Response(export_jsonld(topic), media_type="application/ld+json")
    return Response(export_markdown(topic), media_type="text/markdown")
