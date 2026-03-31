"""Media generation API — TTS audio + video pipeline with SSE progress.

Mirrors the async task + SSE pattern from generate.py.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from ..media.models import KOREAN_VOICES, MediaGenerateRequest
from ..media.pipeline import run_media_pipeline
from ..storage import get_output_dir, load_state

router = APIRouter()
logger = logging.getLogger(__name__)

# Track running media tasks (separate from generation tasks)
_media_tasks: dict[str, asyncio.Task] = {}
_media_queues: dict[str, asyncio.Queue] = {}


@router.get("/{project_id}/media/voices")
async def list_voices():
    """List available Korean TTS voices."""
    return [
        {"id": voice_id, "name": label}
        for voice_id, label in KOREAN_VOICES.items()
    ]


@router.get("/{project_id}/media/debug")
async def media_debug(project_id: str):
    """Debug endpoint: check ffmpeg capabilities."""
    import asyncio as _asyncio
    import shutil as _shutil

    ffmpeg_path = _shutil.which("ffmpeg") or "ffmpeg"
    proc = await _asyncio.create_subprocess_exec(
        ffmpeg_path, "-filters",
        stdout=_asyncio.subprocess.PIPE,
        stderr=_asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    filters_text = stdout.decode("utf-8", errors="replace")

    has_ass = "ass" in filters_text
    has_subtitles = "subtitles" in filters_text
    has_drawtext = "drawtext" in filters_text

    # Check output dir
    output_dir = get_output_dir(project_id)
    media_dir = output_dir / "media"
    media_files = []
    if media_dir.exists():
        media_files = [f.name for f in media_dir.iterdir()]

    return {
        "ffmpeg_path": ffmpeg_path,
        "has_ass_filter": has_ass,
        "has_subtitles_filter": has_subtitles,
        "has_drawtext_filter": has_drawtext,
        "media_files": media_files,
    }


@router.post("/{project_id}/media/generate")
async def start_media_generation(project_id: str, req: MediaGenerateRequest):
    """Start media (audio + video) generation in the background."""
    state = load_state(project_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if not state.chapters_written:
        raise HTTPException(status_code=400, detail="No chapters written yet")

    if project_id in _media_tasks and not _media_tasks[project_id].done():
        raise HTTPException(status_code=409, detail="Media generation already in progress")

    queue: asyncio.Queue = asyncio.Queue()
    _media_queues[project_id] = queue

    async def run_pipeline():
        try:
            output_dir = get_output_dir(project_id)
            current_state = load_state(project_id)

            result = await run_media_pipeline(
                state=current_state,
                output_dir=output_dir,
                options=req,
                progress_queue=queue,
            )

        except Exception as e:
            logger.exception("Media generation failed for %s", project_id)
            queue.put_nowait({"type": "media_error", "message": str(e)})
        finally:
            queue.put_nowait({"type": "end"})

    task = asyncio.create_task(run_pipeline())
    _media_tasks[project_id] = task

    chapters = req.chapters or [ch.chapter for ch in state.chapters_written]
    return {
        "status": "started",
        "project_id": project_id,
        "chapters": chapters,
        "voice": req.voice,
    }


@router.get("/{project_id}/media/stream")
async def stream_media_progress(project_id: str):
    """SSE endpoint for real-time media generation progress."""
    queue = _media_queues.get(project_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="No active media generation")

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


@router.post("/{project_id}/media/stop")
async def stop_media_generation(project_id: str):
    """Stop an in-progress media generation."""
    task = _media_tasks.get(project_id)
    if task is None or task.done():
        raise HTTPException(status_code=404, detail="No active media generation")

    task.cancel()
    _media_tasks.pop(project_id, None)
    _media_queues.pop(project_id, None)
    return {"status": "stopped"}


@router.get("/{project_id}/media/status")
async def media_status(project_id: str):
    """Check media generation status."""
    task = _media_tasks.get(project_id)
    if task is not None:
        if task.done():
            _media_tasks.pop(project_id, None)
            return {"status": "completed"}
        return {"status": "running"}

    # Check if video exists
    output_dir = get_output_dir(project_id)
    video_path = output_dir / "novel_video.mp4"
    if video_path.exists():
        return {
            "status": "ready",
            "file_size_mb": round(video_path.stat().st_size / (1024 * 1024), 1),
        }

    return {"status": "idle"}


@router.get("/{project_id}/media/download")
async def download_video(project_id: str):
    """Download the full novel video."""
    output_dir = get_output_dir(project_id)
    video_path = output_dir / "novel_video.mp4"

    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found — generate first")

    state = load_state(project_id)
    filename = f"novel_video.mp4"
    if state:
        # Use project title for filename
        meta_path = Path(f"data/projects/{project_id}/meta.json")
        if meta_path.exists():
            import json as _json
            meta = _json.loads(meta_path.read_text(encoding="utf-8"))
            title = meta.get("title", "novel")
            filename = f"{title}_video.mp4"

    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
        filename=filename,
    )


@router.get("/{project_id}/media/download/{chapter_num}")
async def download_chapter_video(project_id: str, chapter_num: int):
    """Download a single chapter's video."""
    output_dir = get_output_dir(project_id)
    video_path = output_dir / "media" / f"chapter_{chapter_num:02d}.mp4"

    if not video_path.exists():
        raise HTTPException(status_code=404, detail=f"Chapter {chapter_num} video not found")

    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
        filename=f"chapter_{chapter_num:02d}.mp4",
    )


@router.get("/{project_id}/media/download-audio/{chapter_num}")
async def download_chapter_audio(project_id: str, chapter_num: int):
    """Download a single chapter's audio (MP3)."""
    output_dir = get_output_dir(project_id)
    audio_path = output_dir / "media" / f"chapter_{chapter_num:02d}.mp3"

    if not audio_path.exists():
        raise HTTPException(status_code=404, detail=f"Chapter {chapter_num} audio not found")

    return FileResponse(
        path=str(audio_path),
        media_type="audio/mpeg",
        filename=f"chapter_{chapter_num:02d}.mp3",
    )
