"""Export / download API routes."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

from ..storage import load_state, get_output_dir

router = APIRouter()


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
