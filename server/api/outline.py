"""Plot outline editing API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from novel_maker.models import ChapterOutline

from ..storage import load_state, save_state, get_lock

router = APIRouter()


class OutlineUpdate(BaseModel):
    goal: str | None = None
    key_events: list[str] | None = None
    pov_character: str | None = None
    involved_characters: list[str] | None = None


class OutlineCreate(BaseModel):
    chapter: int
    goal: str
    key_events: list[str] = []
    pov_character: str = ""
    involved_characters: list[str] = []


@router.get("/{project_id}/outline")
async def get_outline(project_id: str):
    """Get the full plot outline."""
    state = load_state(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        "total_chapters": state.total_chapters,
        "outline": [ol.model_dump() for ol in state.plot_outline],
    }


@router.put("/{project_id}/outline")
async def replace_outline(project_id: str, outlines: list[OutlineCreate]):
    """Replace the entire plot outline."""
    async with get_lock(project_id):
        state = load_state(project_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Project not found")
        state.plot_outline = [
            ChapterOutline.model_validate(ol.model_dump()) for ol in outlines
        ]
        state.total_chapters = len(outlines)
        save_state(project_id, state)
    return {"total_chapters": state.total_chapters, "outline": [ol.model_dump() for ol in state.plot_outline]}


@router.put("/{project_id}/outline/{chapter_num}")
async def update_chapter_outline(project_id: str, chapter_num: int, req: OutlineUpdate):
    """Update a single chapter's outline."""
    async with get_lock(project_id):
        state = load_state(project_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Project not found")
        for ol in state.plot_outline:
            if ol.chapter == chapter_num:
                updates = req.model_dump(exclude_none=True)
                for field, value in updates.items():
                    setattr(ol, field, value)
                save_state(project_id, state)
                return ol.model_dump()
    raise HTTPException(status_code=404, detail=f"Chapter {chapter_num} not found")


@router.post("/{project_id}/outline")
async def add_chapter_outline(project_id: str, req: OutlineCreate):
    """Add a new chapter to the outline."""
    async with get_lock(project_id):
        state = load_state(project_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Project not found")
        new_ol = ChapterOutline.model_validate(req.model_dump())
        state.plot_outline.append(new_ol)
        state.plot_outline.sort(key=lambda x: x.chapter)
        state.total_chapters = len(state.plot_outline)
        save_state(project_id, state)
    return new_ol.model_dump()


@router.put("/{project_id}/total-chapters")
async def update_total_chapters(project_id: str, total: int):
    """Update total chapter count."""
    async with get_lock(project_id):
        state = load_state(project_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Project not found")
        state.total_chapters = total
        save_state(project_id, state)
    return {"total_chapters": total}
