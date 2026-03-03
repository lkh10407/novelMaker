"""Export / download API routes."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

from ..storage import load_state, get_output_dir

router = APIRouter()
logger = logging.getLogger(__name__)

# Korean font search paths (system + Docker)
_FONT_SEARCH_PATHS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/OTF/NotoSansCJKkr-Regular.otf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",  # macOS
]


def _find_cjk_font() -> str | None:
    """Find a CJK font on the system."""
    for p in _FONT_SEARCH_PATHS:
        if Path(p).exists():
            return p
    return None


@router.get("/{project_id}/export/markdown")
async def export_markdown(project_id: str):
    """Export full novel as markdown."""
    state = load_state(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if not state.chapters_written:
        raise HTTPException(status_code=404, detail="No chapters written yet")

    parts = [f"# 소설\n\n"]
    for ch in state.chapters_written:
        parts.append(f"## {ch.chapter}장\n\n{ch.content}\n\n---\n\n")

    content = "\n".join(parts)
    return PlainTextResponse(
        content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=novel_{project_id}.md"},
    )


@router.get("/{project_id}/export/epub")
async def export_epub(project_id: str):
    """Export full novel as EPUB."""
    state = load_state(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not state.chapters_written:
        raise HTTPException(status_code=404, detail="No chapters written yet")

    try:
        from ebooklib import epub
    except ImportError:
        raise HTTPException(status_code=500, detail="ebooklib not installed")

    book = epub.EpubBook()
    book.set_identifier(f"novelmaker-{project_id}")
    book.set_title("소설")
    book.set_language("ko")
    book.add_author("NovelMaker AI")

    # CSS for readability
    style = epub.EpubItem(
        uid="style",
        file_name="style/default.css",
        media_type="text/css",
        content=b"body { font-family: serif; line-height: 1.8; } "
                b"h1 { text-align: center; margin-bottom: 2em; } "
                b"p { text-indent: 1em; margin: 0.5em 0; }",
    )
    book.add_item(style)

    chapters = []
    for ch in state.chapters_written:
        # Convert newlines to paragraphs
        paragraphs = "".join(
            f"<p>{line}</p>" for line in ch.content.split("\n") if line.strip()
        )
        epub_ch = epub.EpubHtml(
            title=f"{ch.chapter}장",
            file_name=f"chapter_{ch.chapter:02d}.xhtml",
            lang="ko",
        )
        epub_ch.content = (
            f"<html><body>"
            f"<h1>{ch.chapter}장</h1>"
            f"{paragraphs}"
            f"</body></html>"
        ).encode("utf-8")
        epub_ch.add_item(style)
        book.add_item(epub_ch)
        chapters.append(epub_ch)

    book.toc = [(ch, []) for ch in chapters]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + chapters

    # Write to temp file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".epub")
    epub.write_epub(tmp.name, book)
    tmp.close()

    return FileResponse(
        tmp.name,
        media_type="application/epub+zip",
        filename=f"novel_{project_id}.epub",
    )


@router.get("/{project_id}/export/pdf")
async def export_pdf(project_id: str):
    """Export full novel as PDF."""
    state = load_state(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not state.chapters_written:
        raise HTTPException(status_code=404, detail="No chapters written yet")

    try:
        from fpdf import FPDF
    except ImportError:
        raise HTTPException(status_code=500, detail="fpdf2 not installed")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)

    # Try to load CJK font for Korean support
    font_path = _find_cjk_font()
    font_name = "NotoSansCJK"
    if font_path:
        try:
            pdf.add_font(font_name, "", font_path, uni=True)
        except Exception as e:
            logger.warning("Failed to load CJK font %s: %s", font_path, e)
            font_name = "Helvetica"
    else:
        logger.warning("No CJK font found — PDF may not render Korean text correctly")
        font_name = "Helvetica"

    for ch in state.chapters_written:
        pdf.add_page()
        pdf.set_font(font_name, size=18)
        pdf.cell(0, 15, f"{ch.chapter}장", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(10)

        pdf.set_font(font_name, size=11)
        for line in ch.content.split("\n"):
            if line.strip():
                pdf.multi_cell(0, 7, line.strip())
                pdf.ln(2)
            else:
                pdf.ln(5)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(tmp.name)
    tmp.close()

    return FileResponse(
        tmp.name,
        media_type="application/pdf",
        filename=f"novel_{project_id}.pdf",
    )


@router.get("/{project_id}/export/json")
async def export_json(project_id: str):
    """Export full state as JSON."""
    state = load_state(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return state.model_dump()


@router.get("/{project_id}/export/state-log")
async def export_state_log(project_id: str):
    """Export state change log."""
    log_path = get_output_dir(project_id) / "state_log.json"
    if not log_path.exists():
        return []
    return json.loads(log_path.read_text(encoding="utf-8"))
