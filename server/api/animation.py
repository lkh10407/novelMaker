"""Animation pipeline API — storyboard + dialogue generation with SSE."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from novel_maker.agents.dialogue import generate_dialogue
from novel_maker.agents.storyboard import generate_storyboard
from novel_maker.models import StoryboardScene
from novel_maker.token_tracker import TokenTracker

from ..storage import load_state, save_state

load_dotenv()
router = APIRouter()
logger = logging.getLogger(__name__)

_anim_tasks: dict[str, asyncio.Task] = {}
_anim_queues: dict[str, asyncio.Queue] = {}


class AnimationGenerateRequest(BaseModel):
    model: str | None = None
    chapters: list[int] | None = None  # None = all


@router.post("/{project_id}/animation/generate")
async def start_animation_generation(project_id: str, req: AnimationGenerateRequest):
    """Generate storyboard + dialogue for chapters."""
    state = load_state(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not state.chapters_written:
        raise HTTPException(status_code=400, detail="No chapters written yet")
    if project_id in _anim_tasks and not _anim_tasks[project_id].done():
        raise HTTPException(status_code=409, detail="Animation generation already in progress")

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY not configured")

    model = req.model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    queue: asyncio.Queue = asyncio.Queue()
    _anim_queues[project_id] = queue

    async def run_pipeline():
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            tracker = TokenTracker(model_name=model)

            current_state = load_state(project_id)
            chapters = current_state.chapters_written
            if req.chapters:
                chapters = [ch for ch in chapters if ch.chapter in req.chapters]

            total = len(chapters)

            # Clear existing storyboard/dialogue for regeneration
            if req.chapters:
                ch_set = set(req.chapters)
                current_state.storyboard = [s for s in current_state.storyboard if s.chapter not in ch_set]
                current_state.dialogue_script = [d for d in current_state.dialogue_script if d.chapter not in ch_set]
            else:
                current_state.storyboard = []
                current_state.dialogue_script = []

            for idx, ch in enumerate(chapters):
                ch_num = ch.chapter

                # Storyboard
                queue.put_nowait({
                    "type": "anim_phase",
                    "phase": "storyboard",
                    "chapter": ch_num,
                    "progress": idx / total,
                    "message": f"{ch_num}장 스토리보드 생성 중... ({idx + 1}/{total})",
                })

                scenes = await generate_storyboard(
                    client=client,
                    state=current_state,
                    chapter_num=ch_num,
                    model=model,
                    tracker=tracker,
                )
                current_state.storyboard.extend(scenes)

                queue.put_nowait({
                    "type": "anim_storyboard_complete",
                    "chapter": ch_num,
                    "scene_count": len(scenes),
                    "progress": (idx + 0.5) / total,
                })

                # Dialogue
                queue.put_nowait({
                    "type": "anim_phase",
                    "phase": "dialogue",
                    "chapter": ch_num,
                    "message": f"{ch_num}장 대본 생성 중...",
                })

                lines = await generate_dialogue(
                    client=client,
                    state=current_state,
                    chapter_num=ch_num,
                    storyboard_scenes=scenes,
                    model=model,
                    tracker=tracker,
                )
                current_state.dialogue_script.extend(lines)

                queue.put_nowait({
                    "type": "anim_dialogue_complete",
                    "chapter": ch_num,
                    "line_count": len(lines),
                    "progress": (idx + 1) / total,
                })

                # Save after each chapter
                save_state(project_id, current_state)

            total_scenes = len(current_state.storyboard)
            total_lines = len(current_state.dialogue_script)
            queue.put_nowait({
                "type": "anim_done",
                "total_scenes": total_scenes,
                "total_lines": total_lines,
                "total_tokens": tracker.total_tokens,
                "cost_usd": round(tracker.estimated_cost_usd, 4),
            })

        except Exception as e:
            logger.exception("Animation generation failed for %s", project_id)
            queue.put_nowait({"type": "anim_error", "message": str(e)})
        finally:
            queue.put_nowait({"type": "end"})

    task = asyncio.create_task(run_pipeline())
    _anim_tasks[project_id] = task

    chapter_nums = req.chapters or [ch.chapter for ch in state.chapters_written]
    return {"status": "started", "chapters": chapter_nums}


@router.get("/{project_id}/animation/stream")
async def stream_animation_progress(project_id: str):
    """SSE endpoint for animation generation progress."""
    queue = _anim_queues.get(project_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="No active animation generation")

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                yield {
                    "event": event.get("type", "message"),
                    "data": json.dumps(event, ensure_ascii=False),
                }
                if event.get("type") == "end":
                    break
        except Exception:
            pass

    return EventSourceResponse(event_generator())


@router.post("/{project_id}/animation/stop")
async def stop_animation_generation(project_id: str):
    """Stop animation generation."""
    task = _anim_tasks.get(project_id)
    if task is None or task.done():
        raise HTTPException(status_code=404, detail="No active generation")
    task.cancel()
    _anim_tasks.pop(project_id, None)
    _anim_queues.pop(project_id, None)
    return {"status": "stopped"}


@router.get("/{project_id}/animation/status")
async def animation_status(project_id: str):
    """Check animation generation status."""
    task = _anim_tasks.get(project_id)
    if task is not None:
        if task.done():
            _anim_tasks.pop(project_id, None)
            return {"status": "completed"}
        return {"status": "running"}

    state = load_state(project_id)
    if state and state.storyboard:
        return {
            "status": "ready",
            "scene_count": len(state.storyboard),
            "line_count": len(state.dialogue_script),
        }
    return {"status": "idle"}


# ---- Storyboard CRUD ----

@router.get("/{project_id}/storyboard")
async def list_storyboard(project_id: str):
    """Get all storyboard scenes."""
    state = load_state(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return [s.model_dump() for s in state.storyboard]


@router.get("/{project_id}/storyboard/{chapter_num}")
async def get_chapter_storyboard(project_id: str, chapter_num: int):
    """Get storyboard scenes for a specific chapter."""
    state = load_state(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")
    scenes = [s.model_dump() for s in state.storyboard if s.chapter == chapter_num]
    return scenes


class StoryboardUpdateRequest(BaseModel):
    visual_description: str | None = None
    image_prompt: str | None = None
    camera_angle: str | None = None
    mood: str | None = None
    duration_seconds: float | None = None


@router.put("/{project_id}/storyboard/{chapter_num}/{scene_num}")
async def update_storyboard_scene(
    project_id: str, chapter_num: int, scene_num: int, req: StoryboardUpdateRequest,
):
    """Update a specific storyboard scene."""
    state = load_state(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    for scene in state.storyboard:
        if scene.chapter == chapter_num and scene.scene_number == scene_num:
            updates = req.model_dump(exclude_none=True)
            for field, value in updates.items():
                setattr(scene, field, value)
            save_state(project_id, state)
            return scene.model_dump()

    raise HTTPException(status_code=404, detail="Scene not found")


# ---- Dialogue CRUD ----

@router.get("/{project_id}/dialogue")
async def list_dialogue(project_id: str):
    """Get all dialogue lines."""
    state = load_state(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return [d.model_dump() for d in state.dialogue_script]


@router.get("/{project_id}/dialogue/{chapter_num}")
async def get_chapter_dialogue(project_id: str, chapter_num: int):
    """Get dialogue lines for a specific chapter."""
    state = load_state(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")
    lines = [d.model_dump() for d in state.dialogue_script if d.chapter == chapter_num]
    return lines
