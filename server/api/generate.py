"""Novel generation API with SSE streaming progress."""

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

from novel_maker.models import NovelState
from novel_maker.workflow import NovelPipeline

from ..storage import load_state, save_state, get_output_dir

load_dotenv()
router = APIRouter()
logger = logging.getLogger(__name__)

# Track running generation tasks
_running_tasks: dict[str, asyncio.Task] = {}
_progress_queues: dict[str, asyncio.Queue] = {}
_approval_queues: dict[str, asyncio.Queue] = {}


class GenerateRequest(BaseModel):
    total_chapters: int | None = None
    model: str | None = None
    language: str = "ko"
    interactive: bool = True


class ApprovalRequest(BaseModel):
    approved: bool = True
    edited_content: str | None = None
    guidance: str = ""


@router.post("/{project_id}/generate")
async def start_generation(project_id: str, req: GenerateRequest):
    """Start novel generation in the background."""
    state = load_state(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if project_id in _running_tasks and not _running_tasks[project_id].done():
        raise HTTPException(status_code=409, detail="Generation already in progress")

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY not configured")

    model = req.model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    total_chapters = req.total_chapters or state.total_chapters or 3

    # Create progress queue
    queue: asyncio.Queue = asyncio.Queue()
    _progress_queues[project_id] = queue

    # Create approval queue for interactive mode
    approval_queue: asyncio.Queue | None = None
    if req.interactive:
        approval_queue = asyncio.Queue()
        _approval_queues[project_id] = approval_queue

    async def run_pipeline():
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            output_dir = get_output_dir(project_id)

            pipeline = NovelPipeline(
                client=client,
                model=model,
                output_dir=output_dir,
            )

            # Wire HITL approval queue
            if approval_queue is not None:
                pipeline.approval_queue = approval_queue

            # Initialize RAG memory store
            from novel_maker.memory import MemoryStore
            pipeline.memory_store = MemoryStore(
                project_dir=Path(f"data/projects/{project_id}"),
                client=client,
            )

            # Wire up progress callbacks
            def on_phase_change(phase: str, **kwargs):
                # Send awaiting_approval as its own SSE event type
                event_type = "awaiting_approval" if phase == "awaiting_approval" else "phase"
                event = {"type": event_type, "phase": phase, **kwargs}
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass

            def on_chapter_complete(ch_num, result):
                event = {
                    "type": "chapter_complete",
                    "chapter": ch_num,
                    "summary": result.summary,
                    "char_count": result.char_count,
                }
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass

            pipeline.on_phase_change = on_phase_change
            pipeline.on_chapter_complete = on_chapter_complete

            # Load existing state and project meta
            current_state = load_state(project_id)
            meta_path = Path(f"data/projects/{project_id}/meta.json")
            logline = ""
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                logline = meta.get("logline", "")

            final_state = await pipeline.run(
                logline=logline,
                total_chapters=total_chapters,
                language=req.language,
                existing_state=current_state,
            )

            # Save final state back
            save_state(project_id, final_state)

            queue.put_nowait({
                "type": "done",
                "total_tokens": pipeline.tracker.total_tokens,
                "cost_usd": round(pipeline.tracker.estimated_cost_usd, 4),
            })

        except Exception as e:
            logger.exception("Generation failed for %s", project_id)
            queue.put_nowait({"type": "error", "message": str(e)})
        finally:
            queue.put_nowait({"type": "end"})
            _approval_queues.pop(project_id, None)

    task = asyncio.create_task(run_pipeline())
    _running_tasks[project_id] = task

    return {"status": "started", "project_id": project_id}


@router.get("/{project_id}/generate/stream")
async def stream_progress(project_id: str):
    """SSE endpoint for real-time generation progress."""
    queue = _progress_queues.get(project_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="No active generation")

    async def event_generator():
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=120)
                yield {
                    "event": event.get("type", "message"),
                    "data": json.dumps(event, ensure_ascii=False),
                }
                if event.get("type") == "end":
                    break
        except asyncio.TimeoutError:
            yield {"event": "timeout", "data": "{}"}
        finally:
            _progress_queues.pop(project_id, None)

    return EventSourceResponse(event_generator())


@router.post("/{project_id}/generate/stop")
async def stop_generation(project_id: str):
    """Stop an in-progress generation."""
    task = _running_tasks.get(project_id)
    if task is None or task.done():
        raise HTTPException(status_code=404, detail="No active generation")

    task.cancel()
    _running_tasks.pop(project_id, None)
    _progress_queues.pop(project_id, None)
    _approval_queues.pop(project_id, None)
    return {"status": "stopped"}


@router.post("/{project_id}/generate/approve/{chapter_num}")
async def approve_chapter(project_id: str, chapter_num: int, req: ApprovalRequest):
    """Approve (or edit) a chapter and resume generation."""
    approval_queue = _approval_queues.get(project_id)
    if approval_queue is None:
        raise HTTPException(
            status_code=404,
            detail="No pending approval for this project",
        )

    approval_data = {
        "approved": req.approved,
        "edited_content": req.edited_content,
        "guidance": req.guidance,
    }
    await approval_queue.put(approval_data)
    return {"status": "approved", "chapter": chapter_num}


@router.get("/{project_id}/generate/status")
async def generation_status(project_id: str):
    """Check generation status."""
    task = _running_tasks.get(project_id)
    if task is None:
        return {"status": "idle"}
    if task.done():
        _running_tasks.pop(project_id, None)
        return {"status": "completed"}
    return {"status": "running"}


@router.get("/{project_id}/chapters")
async def list_chapters(project_id: str):
    """List written chapters."""
    state = load_state(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return [
        {
            "chapter": ch.chapter,
            "summary": ch.summary,
            "char_count": ch.char_count,
            "ending_hook": ch.ending_hook,
        }
        for ch in state.chapters_written
    ]


@router.get("/{project_id}/chapters/{chapter_num}")
async def get_chapter(project_id: str, chapter_num: int):
    """Get a single chapter's full content."""
    state = load_state(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")
    for ch in state.chapters_written:
        if ch.chapter == chapter_num:
            return ch.model_dump()
    raise HTTPException(status_code=404, detail=f"Chapter {chapter_num} not found")


@router.get("/{project_id}/tokens")
async def get_token_usage(project_id: str):
    """Get token usage data."""
    token_path = get_output_dir(project_id) / "token_usage.json"
    if not token_path.exists():
        return {"total_input_tokens": 0, "total_output_tokens": 0, "records": []}
    return json.loads(token_path.read_text(encoding="utf-8"))
