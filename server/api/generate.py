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

from ..storage import load_state, save_state, get_output_dir, get_lock

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
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection alive
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
        finally:
            # Don't remove queue here — allow reconnection
            pass

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


class ChapterUpdateRequest(BaseModel):
    content: str | None = None
    summary: str | None = None


@router.put("/{project_id}/chapters/{chapter_num}")
async def update_chapter(project_id: str, chapter_num: int, req: ChapterUpdateRequest):
    """Update a chapter's content and/or summary after generation."""
    async with get_lock(project_id):
        state = load_state(project_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Project not found")
        for ch in state.chapters_written:
            if ch.chapter == chapter_num:
                if req.content is not None:
                    ch.content = req.content
                    ch.char_count = len(req.content)
                if req.summary is not None:
                    ch.summary = req.summary
                save_state(project_id, state)
                # Also update the markdown file
                ch_path = get_output_dir(project_id) / f"chapter_{chapter_num:02d}.md"
                if ch_path.exists():
                    ch_path.write_text(
                        f"# {chapter_num}장\n\n{ch.content}",
                        encoding="utf-8",
                    )
                return ch.model_dump()
        raise HTTPException(status_code=404, detail=f"Chapter {chapter_num} not found")


@router.get("/{project_id}/generate/status")
async def generation_status(project_id: str):
    """Check generation status.

    Also checks persisted state phase for cases where the server
    restarted and in-memory task was lost.
    """
    task = _running_tasks.get(project_id)
    if task is not None:
        if task.done():
            _running_tasks.pop(project_id, None)
            return {"status": "completed"}
        return {"status": "running"}

    # Check persisted state for resumable generation
    state = load_state(project_id)
    if state is not None and state.phase not in ("planning", "done"):
        return {
            "status": "interrupted",
            "phase": state.phase,
            "current_chapter": state.current_chapter,
            "total_chapters": state.total_chapters,
        }
    return {"status": "idle"}


@router.post("/{project_id}/generate/resume")
async def resume_generation(project_id: str, req: GenerateRequest):
    """Resume an interrupted generation from the last checkpoint.

    This is useful after a server restart when an in-memory task was lost
    but the state was saved to disk with chapters already written.
    """
    state = load_state(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if state.phase == "done":
        raise HTTPException(status_code=400, detail="Generation already completed")

    if not state.chapters_written and not state.characters:
        raise HTTPException(status_code=400, detail="No progress to resume — use /generate instead")

    if project_id in _running_tasks and not _running_tasks[project_id].done():
        raise HTTPException(status_code=409, detail="Generation already in progress")

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY not configured")

    model = req.model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    total_chapters = req.total_chapters or state.total_chapters or 3

    queue: asyncio.Queue = asyncio.Queue()
    _progress_queues[project_id] = queue

    approval_queue: asyncio.Queue | None = None
    if req.interactive:
        approval_queue = asyncio.Queue()
        _approval_queues[project_id] = approval_queue

    async def run_resume():
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            output_dir = get_output_dir(project_id)

            pipeline = NovelPipeline(
                client=client,
                model=model,
                output_dir=output_dir,
            )

            if approval_queue is not None:
                pipeline.approval_queue = approval_queue

            from novel_maker.memory import MemoryStore
            pipeline.memory_store = MemoryStore(
                project_dir=Path(f"data/projects/{project_id}"),
                client=client,
            )

            def on_phase_change(phase: str, **kwargs):
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

            current_state = load_state(project_id)
            meta_path = Path(f"data/projects/{project_id}/meta.json")
            logline = ""
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                logline = meta.get("logline", "")

            queue.put_nowait({
                "type": "phase",
                "phase": "resumed",
                "chapter": current_state.current_chapter,
            })

            final_state = await pipeline.run(
                logline=logline,
                total_chapters=total_chapters,
                language=req.language,
                existing_state=current_state,
            )

            save_state(project_id, final_state)

            queue.put_nowait({
                "type": "done",
                "total_tokens": pipeline.tracker.total_tokens,
                "cost_usd": round(pipeline.tracker.estimated_cost_usd, 4),
            })

        except Exception as e:
            logger.exception("Resume failed for %s", project_id)
            queue.put_nowait({"type": "error", "message": str(e)})
        finally:
            queue.put_nowait({"type": "end"})
            _approval_queues.pop(project_id, None)

    task = asyncio.create_task(run_resume())
    _running_tasks[project_id] = task

    return {
        "status": "resumed",
        "project_id": project_id,
        "from_chapter": state.current_chapter,
    }


class RegenerateRequest(BaseModel):
    guidance: str = ""
    model: str | None = None


@router.post("/{project_id}/chapters/{chapter_num}/regenerate")
async def regenerate_chapter_endpoint(project_id: str, chapter_num: int, req: RegenerateRequest):
    """Regenerate a specific chapter."""
    state = load_state(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    existing = None
    for ch in state.chapters_written:
        if ch.chapter == chapter_num:
            existing = ch
            break
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Chapter {chapter_num} not found")

    if project_id in _running_tasks and not _running_tasks[project_id].done():
        raise HTTPException(status_code=409, detail="Generation already in progress")

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY not configured")

    model = req.model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    queue: asyncio.Queue = asyncio.Queue()
    _progress_queues[project_id] = queue

    async def run_regen():
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            output_dir = get_output_dir(project_id)

            pipeline = NovelPipeline(
                client=client,
                model=model,
                output_dir=output_dir,
            )

            def on_phase_change(phase: str, **kwargs):
                event = {"type": "phase", "phase": phase, **kwargs}
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass

            pipeline.on_phase_change = on_phase_change

            current_state = load_state(project_id)
            final_state = await pipeline.regenerate_chapter(
                state=current_state,
                chapter_num=chapter_num,
                guidance=req.guidance,
            )

            save_state(project_id, final_state)

            # Find the new chapter result
            new_ch = None
            for ch in final_state.chapters_written:
                if ch.chapter == chapter_num:
                    new_ch = ch
                    break

            queue.put_nowait({
                "type": "chapter_complete",
                "chapter": chapter_num,
                "summary": new_ch.summary if new_ch else "",
                "char_count": new_ch.char_count if new_ch else 0,
            })
            queue.put_nowait({
                "type": "done",
                "total_tokens": pipeline.tracker.total_tokens,
                "cost_usd": round(pipeline.tracker.estimated_cost_usd, 4),
            })
        except Exception as e:
            logger.exception("Regeneration failed for %s ch%d", project_id, chapter_num)
            queue.put_nowait({"type": "error", "message": str(e)})
        finally:
            queue.put_nowait({"type": "end"})

    task = asyncio.create_task(run_regen())
    _running_tasks[project_id] = task

    return {"status": "started", "chapter": chapter_num}


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
            "version": getattr(ch, "version", 1),
            "has_branches": str(ch.chapter) in (state.chapter_branches or {}),
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


# -- Chapter branches (What-if) --

class BranchRequest(BaseModel):
    guidance: str = ""
    model: str | None = None


@router.post("/{project_id}/chapters/{chapter_num}/branch")
async def create_branch(project_id: str, chapter_num: int, req: BranchRequest):
    """Create a new branch (alternative version) of a chapter."""
    state = load_state(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    existing = None
    for ch in state.chapters_written:
        if ch.chapter == chapter_num:
            existing = ch
            break
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Chapter {chapter_num} not found")

    if project_id in _running_tasks and not _running_tasks[project_id].done():
        raise HTTPException(status_code=409, detail="Generation already in progress")

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY not configured")

    model = req.model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    queue: asyncio.Queue = asyncio.Queue()
    _progress_queues[project_id] = queue

    async def run_branch():
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            output_dir = get_output_dir(project_id)

            pipeline = NovelPipeline(
                client=client,
                model=model,
                output_dir=output_dir,
            )

            def on_phase_change(phase: str, **kwargs):
                event = {"type": "phase", "phase": phase, **kwargs}
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass

            pipeline.on_phase_change = on_phase_change

            current_state = load_state(project_id)

            # Temporarily set current_chapter and generate
            original_current = current_state.current_chapter
            current_state.current_chapter = chapter_num
            current_state.user_guidance = req.guidance

            current_state, new_result = await pipeline._process_single_chapter(
                current_state, skip_finalize=True,
            )

            current_state.current_chapter = original_current
            current_state.current_draft = ""
            current_state.user_guidance = ""

            # Calculate next version number
            ch_key = str(chapter_num)
            if ch_key not in current_state.chapter_branches:
                current_state.chapter_branches[ch_key] = []

            # Add current active chapter as v1 if branches is empty
            if not current_state.chapter_branches[ch_key]:
                for ch in current_state.chapters_written:
                    if ch.chapter == chapter_num:
                        v1_copy = ch.model_copy()
                        v1_copy.version = 1
                        current_state.chapter_branches[ch_key].append(v1_copy)
                        break

            max_ver = max(
                (b.version for b in current_state.chapter_branches[ch_key]),
                default=0,
            )
            new_result.version = max_ver + 1
            current_state.chapter_branches[ch_key].append(new_result)

            save_state(project_id, current_state)

            queue.put_nowait({
                "type": "chapter_complete",
                "chapter": chapter_num,
                "version": new_result.version,
                "summary": new_result.summary,
                "char_count": new_result.char_count,
            })
            queue.put_nowait({
                "type": "done",
                "total_tokens": pipeline.tracker.total_tokens,
                "cost_usd": round(pipeline.tracker.estimated_cost_usd, 4),
            })
        except Exception as e:
            logger.exception("Branch creation failed for %s ch%d", project_id, chapter_num)
            queue.put_nowait({"type": "error", "message": str(e)})
        finally:
            queue.put_nowait({"type": "end"})

    task = asyncio.create_task(run_branch())
    _running_tasks[project_id] = task

    return {"status": "started", "chapter": chapter_num}


@router.get("/{project_id}/chapters/{chapter_num}/branches")
async def list_branches(project_id: str, chapter_num: int):
    """List all branch versions of a chapter."""
    state = load_state(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    ch_key = str(chapter_num)
    branches = state.chapter_branches.get(ch_key, [])
    return [
        {
            "version": b.version,
            "summary": b.summary,
            "char_count": b.char_count,
            "content": b.content,
        }
        for b in branches
    ]


@router.post("/{project_id}/chapters/{chapter_num}/branches/{version}/adopt")
async def adopt_branch(project_id: str, chapter_num: int, version: int):
    """Adopt a specific branch version as the active chapter."""
    async with get_lock(project_id):
        state = load_state(project_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Project not found")

        ch_key = str(chapter_num)
        branches = state.chapter_branches.get(ch_key, [])
        target = None
        for b in branches:
            if b.version == version:
                target = b
                break
        if target is None:
            raise HTTPException(status_code=404, detail=f"Version {version} not found")

        # Replace the active chapter
        for i, ch in enumerate(state.chapters_written):
            if ch.chapter == chapter_num:
                adopted = target.model_copy()
                state.chapters_written[i] = adopted
                break

        # Update markdown file
        ch_path = get_output_dir(project_id) / f"chapter_{chapter_num:02d}.md"
        if ch_path.exists():
            ch_path.write_text(
                f"# {chapter_num}장\n\n{target.content}",
                encoding="utf-8",
            )

        save_state(project_id, state)

    return {"status": "adopted", "chapter": chapter_num, "version": version}
