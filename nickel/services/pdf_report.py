"""PDF-отчёт с кириллицей (DejaVu/Arial) и таблицами."""

from __future__ import annotations

import platform
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

_FONT_REGISTERED = False
FONT_REGULAR = "ReportRegular"
FONT_BOLD = "ReportBold"


def _font_candidates() -> List[Tuple[Path, Path]]:
    pairs: List[Tuple[Path, Path]] = []

    bundled_r = ASSETS_DIR / "DejaVuSans.ttf"
    bundled_b = ASSETS_DIR / "DejaVuSans-Bold.ttf"
    if bundled_r.exists():
        pairs.append((bundled_r, bundled_b if bundled_b.exists() else bundled_r))

    if platform.system() == "Windows":
        win = Path("C:/Windows/Fonts")
        for reg, bold in (
            ("arial.ttf", "arialbd.ttf"),
            ("segoeui.ttf", "segoeuib.ttf"),
            ("calibri.ttf", "calibrib.ttf"),
        ):
            r, b = win / reg, win / bold
            if r.exists():
                pairs.append((r, b if b.exists() else r))
    else:
        dejavu = Path("/usr/share/fonts/truetype/dejavu")
        r, b = dejavu / "DejaVuSans.ttf", dejavu / "DejaVuSans-Bold.ttf"
        if r.exists():
            pairs.append((r, b if b.exists() else r))
        lib = Path("/usr/share/fonts/truetype/liberation")
        r2, b2 = lib / "LiberationSans-Regular.ttf", lib / "LiberationSans-Bold.ttf"
        if r2.exists():
            pairs.append((r2, b2 if b2.exists() else r2))

    return pairs


def ensure_cyrillic_fonts() -> None:
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return
    for regular, bold in _font_candidates():
        try:
            pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(regular)))
            pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold)))
            _FONT_REGISTERED = True
            return
        except Exception:
            continue
    raise RuntimeError(
        "Cyrillic font not found. Install fonts-dejavu-core (Linux) or add "
        "DejaVuSans.ttf to nickel/assets/fonts/"
    )


def _styles() -> Dict[str, ParagraphStyle]:
    ensure_cyrillic_fonts()
    return {
        "title": ParagraphStyle(
            "Title", fontName=FONT_BOLD, fontSize=18, leading=22,
            alignment=TA_CENTER, spaceAfter=12,
        ),
        "h2": ParagraphStyle(
            "H2", fontName=FONT_BOLD, fontSize=13, leading=16, spaceBefore=14, spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "Body", fontName=FONT_REGULAR, fontSize=10, leading=14,
        ),
        "small": ParagraphStyle(
            "Small", fontName=FONT_REGULAR, fontSize=8, leading=10, textColor=colors.grey,
        ),
        "cell": ParagraphStyle(
            "Cell", fontName=FONT_REGULAR, fontSize=9, leading=12,
        ),
        "cell_hdr": ParagraphStyle(
            "CellHdr", fontName=FONT_BOLD, fontSize=9, leading=12, textColor=colors.white,
        ),
    }


def _p(text: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(text if text is not None else "—")), style)


def _table(headers: List[str], rows: List[List[Any]], col_widths: Optional[List[float]] = None) -> Table:
    st = _styles()
    data = [[_p(h, st["cell_hdr"]) for h in headers]]
    for row in rows:
        data.append([_p(c, st["cell"]) for c in row])

    if not col_widths:
        avail = 17 * cm
        col_widths = [avail / len(headers)] * len(headers)

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a365d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def build_pdf_report(topic: str, review: Dict[str, Any]) -> bytes:
    ensure_cyrillic_fonts()
    st = _styles()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"LitReview-{topic[:40]}",
    )
    story: list = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    story.append(_p("Литературный обзор R&D Knowledge Graph", st["title"]))
    story.append(_p(topic, st["h2"]))
    story.append(Spacer(1, 6))

    meta_rows = [
        ["Уверенность", f"{review.get('confidence', 0):.0%}"],
        ["Источников", str(review.get("sources_count", 0))],
        ["Верифицировано", str(review.get("verified_sources", 0))],
        ["Режим синтеза", review.get("synthesis_mode", "structured")],
        ["LLM", "да" if review.get("llm_synthesized") else "нет"],
        ["Дата экспорта", now],
    ]
    if review.get("years_present"):
        meta_rows.append(["Годы в данных", ", ".join(str(y) for y in review["years_present"][:8])])

    story.append(_p("Сводка", st["h2"]))
    story.append(_table(["Параметр", "Значение"], meta_rows, [5 * cm, 12 * cm]))
    story.append(Spacer(1, 12))

    story.append(_p("Резюме", st["h2"]))
    for para in (review.get("summary") or "").split("\n\n"):
        para = para.strip()
        if para:
            story.append(_p(para.replace("\n", "<br/>"), st["body"]))
            story.append(Spacer(1, 6))

    year_summary = review.get("year_summary") or {}
    if year_summary:
        story.append(_p("Динамика по годам", st["h2"]))
        rows = [
            [year, info.get("count", 0), info.get("facts", 0)]
            for year, info in sorted(year_summary.items(), key=lambda x: str(x[0]), reverse=True)
            if str(year) != "unknown"
        ]
        if rows:
            story.append(_table(["Год", "Записей", "Фактов"], rows, [3 * cm, 4 * cm, 4 * cm]))
            story.append(Spacer(1, 10))

    by_geo = review.get("by_geography") or {}
    if by_geo:
        story.append(_p("География", st["h2"]))
        story.append(_table(
            ["География", "Фактов"],
            [[k, v] for k, v in by_geo.items()],
            [8 * cm, 4 * cm],
        ))
        story.append(Spacer(1, 10))

    by_src = review.get("by_source_type") or {}
    if by_src:
        story.append(_p("Типы источников", st["h2"]))
        rows = [
            [info.get("label", key), info.get("count", 0), info.get("verified_count", 0)]
            for key, info in by_src.items()
        ]
        story.append(_table(["Тип", "Всего", "Верифиц."], rows, [8 * cm, 3 * cm, 3 * cm]))
        story.append(Spacer(1, 10))

    consensus = review.get("consensus_findings") or []
    if consensus:
        story.append(_p("Консенсусные выводы", st["h2"]))
        rows = []
        for f in consensus[:15]:
            prov = f.get("provenance") or {}
            rows.append([
                f.get("subject", ""),
                f.get("relation", ""),
                f.get("object", ""),
                prov.get("source_document") or f.get("source_document", ""),
                prov.get("year") or (f.get("properties") or {}).get("year", ""),
            ])
        story.append(_table(
            ["Субъект", "Связь", "Объект", "Источник", "Год"],
            rows, [3.5 * cm, 2.5 * cm, 3.5 * cm, 3.5 * cm, 1.5 * cm],
        ))
        story.append(Spacer(1, 10))

    disagreements = review.get("disagreements") or []
    if disagreements:
        story.append(_p("Зоны разногласий", st["h2"]))
        rows = [[f.get("subject"), f.get("relation"), f.get("object")] for f in disagreements[:10]]
        story.append(_table(["Субъект", "Связь", "Объект"], rows, [5 * cm, 3 * cm, 5 * cm]))
        story.append(Spacer(1, 10))

    excerpts = review.get("document_excerpts") or []
    if excerpts:
        story.append(_p("Фрагменты документов", st["h2"]))
        rows = [[c.get("document", "—"), (c.get("text") or "")[:200]] for c in excerpts[:8]]
        story.append(_table(["Документ", "Фрагмент"], rows, [4 * cm, 13 * cm]))

    story.append(Spacer(1, 20))
    story.append(_p("Сгенерировано Nickel R&D Knowledge Graph Platform", st["small"]))

    doc.build(story)
    return buffer.getvalue()
