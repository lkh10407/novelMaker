"""World settings API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from novel_maker.models import Foreshadowing

from ..storage import load_state, save_state, get_lock

router = APIRouter()


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
