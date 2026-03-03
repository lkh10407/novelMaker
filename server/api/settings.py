"""World settings API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from novel_maker.models import Foreshadowing

from ..storage import load_state, save_state, get_lock

router = APIRouter()

MAX_STYLE_REF_SIZE = 50_000  # 50KB text limit


class WorldSettingsUpdate(BaseModel):
    tone: str | None = None
    rules: list[str] | None = None
    locations: list[str] | None = None
    time_period: str | None = None


class ForeshadowingCreate(BaseModel):
    planted_chapter: int
    description: str


@router.get("/{project_id}/settings")
async def get_settings(project_id: str):
    """Get world settings."""
    state = load_state(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return state.world_setting.model_dump()


@router.put("/{project_id}/settings")
async def update_settings(project_id: str, req: WorldSettingsUpdate):
    """Update world settings."""
    async with get_lock(project_id):
        state = load_state(project_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Project not found")
        updates = req.model_dump(exclude_none=True)
        for field, value in updates.items():
            setattr(state.world_setting, field, value)
        save_state(project_id, state)
    return state.world_setting.model_dump()


# -- Foreshadowing --

@router.get("/{project_id}/foreshadowing")
async def list_foreshadowing(project_id: str):
    """List all foreshadowing elements."""
    state = load_state(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return [f.model_dump() for f in state.foreshadowing]


@router.post("/{project_id}/foreshadowing")
async def add_foreshadowing(project_id: str, req: ForeshadowingCreate):
    """Add a foreshadowing element."""
    async with get_lock(project_id):
        state = load_state(project_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Project not found")
        max_id = max((f.id for f in state.foreshadowing), default=0)
        new_fs = Foreshadowing(
            id=max_id + 1,
            planted_chapter=req.planted_chapter,
            description=req.description,
        )
        state.foreshadowing.append(new_fs)
        save_state(project_id, state)
    return new_fs.model_dump()


class ForeshadowingUpdate(BaseModel):
    resolved: bool | None = None
    resolved_chapter: int | None = None


@router.put("/{project_id}/foreshadowing/{fs_id}")
async def update_foreshadowing(project_id: str, fs_id: int, req: ForeshadowingUpdate):
    """Update foreshadowing resolution status."""
    async with get_lock(project_id):
        state = load_state(project_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Project not found")
        for f in state.foreshadowing:
            if f.id == fs_id:
                if req.resolved is not None:
                    f.resolved = req.resolved
                if req.resolved_chapter is not None:
                    f.resolved_chapter = req.resolved_chapter
                save_state(project_id, state)
                return f.model_dump()
        raise HTTPException(status_code=404, detail="Foreshadowing not found")


@router.delete("/{project_id}/foreshadowing/{fs_id}")
async def delete_foreshadowing(project_id: str, fs_id: int):
    """Delete a foreshadowing element."""
    async with get_lock(project_id):
        state = load_state(project_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Project not found")
        state.foreshadowing = [f for f in state.foreshadowing if f.id != fs_id]
        save_state(project_id, state)
    return {"status": "deleted"}


# -- Style reference --

@router.get("/{project_id}/style-reference")
async def get_style_reference(project_id: str):
    """Get the style reference text."""
    state = load_state(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"text": state.style_reference}


@router.post("/{project_id}/style-reference")
async def upload_style_reference(project_id: str, file: UploadFile = File(...)):
    """Upload a style reference text file (.txt/.md)."""
    if file.content_type and file.content_type not in (
        "text/plain", "text/markdown", "application/octet-stream",
    ):
        raise HTTPException(status_code=400, detail="Only .txt/.md files are supported")

    content = await file.read()
    if len(content) > MAX_STYLE_REF_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large (max {MAX_STYLE_REF_SIZE // 1000}KB)")

    text = content.decode("utf-8", errors="replace")

    async with get_lock(project_id):
        state = load_state(project_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Project not found")
        state.style_reference = text
        save_state(project_id, state)

    return {"status": "uploaded", "char_count": len(text)}


@router.delete("/{project_id}/style-reference")
async def delete_style_reference(project_id: str):
    """Delete the style reference."""
    async with get_lock(project_id):
        state = load_state(project_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Project not found")
        state.style_reference = ""
        save_state(project_id, state)
    return {"status": "deleted"}
