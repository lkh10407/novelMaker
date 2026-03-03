"""Character management API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from novel_maker.models import Character

from ..storage import load_state, save_state, get_lock

router = APIRouter()


class CharacterCreate(BaseModel):
    name: str
    traits: str = ""
    status: str = "alive"
    location: str = ""
    inventory: list[str] = []
    relationships: dict[str, str] = {}


class CharacterUpdate(BaseModel):
    name: str | None = None
    traits: str | None = None
    status: str | None = None
    location: str | None = None
    inventory: list[str] | None = None
    relationships: dict[str, str] | None = None


def _get_state_or_404(project_id: str):
    state = load_state(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return state


@router.get("/{project_id}/characters")
async def list_characters(project_id: str):
    """List all characters in a project."""
    state = _get_state_or_404(project_id)
    return [ch.model_dump() for ch in state.characters]


@router.post("/{project_id}/characters")
async def add_character(project_id: str, req: CharacterCreate):
    """Add a new character."""
    async with get_lock(project_id):
        state = _get_state_or_404(project_id)
        max_id = max((ch.id for ch in state.characters), default=0)
        new_char = Character(
            id=max_id + 1,
            name=req.name,
            traits=req.traits,
            status=req.status,
            location=req.location,
            inventory=req.inventory,
            relationships=req.relationships,
        )
        state.characters.append(new_char)
        save_state(project_id, state)
    return new_char.model_dump()


@router.get("/{project_id}/characters/{char_id}")
async def get_character(project_id: str, char_id: int):
    """Get a single character."""
    state = _get_state_or_404(project_id)
    for ch in state.characters:
        if ch.id == char_id:
            return ch.model_dump()
    raise HTTPException(status_code=404, detail="Character not found")


@router.put("/{project_id}/characters/{char_id}")
async def update_character(project_id: str, char_id: int, req: CharacterUpdate):
    """Update a character."""
    async with get_lock(project_id):
        state = _get_state_or_404(project_id)
        for ch in state.characters:
            if ch.id == char_id:
                updates = req.model_dump(exclude_none=True)
                for field, value in updates.items():
                    setattr(ch, field, value)
                save_state(project_id, state)
                return ch.model_dump()
    raise HTTPException(status_code=404, detail="Character not found")


@router.delete("/{project_id}/characters/{char_id}")
async def delete_character(project_id: str, char_id: int):
    """Delete a character."""
    async with get_lock(project_id):
        state = _get_state_or_404(project_id)
        state.characters = [ch for ch in state.characters if ch.id != char_id]
        save_state(project_id, state)
    return {"status": "deleted"}
