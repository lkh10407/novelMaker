"""Media pipeline orchestrator — coordinates TTS → subtitle → video flow.

Mirrors the pattern of workflow.py but for media generation.
Each phase sends progress events to an asyncio.Queue for SSE streaming.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from novel_maker.models import NovelState

from .models import ChapterVideoResult, MediaGenerateRequest, MediaResult
from .subtitles import vtt_to_ass
from .tts import generate_chapter_audio
from .video import (
    compose_chapter_video,
    concatenate_videos,
    generate_title_card_video,
    get_audio_duration,
)

# Import storage backend for syncing media to GCS
from ..storage import _backend as storage_backend

logger = logging.getLogger(__name__)

TITLE_CARD_DURATION = 4.0  # seconds


async def run_media_pipeline(
    state: NovelState,
    output_dir: Path,
    options: MediaGenerateRequest,
    progress_queue: asyncio.Queue,
) -> MediaResult:
    """Run the full media generation pipeline.

    Flow per chapter:
        1. TTS → MP3 + VTT
        2. VTT → ASS styled subtitle
        3. (Optional) Title card video
        4. Background + audio + subtitle → chapter MP4

    Then concatenate all chapter videos into final MP4.

    Args:
        state: NovelState with chapters_written.
        output_dir: Directory for intermediate and final files.
        options: User configuration (voice, colors, etc).
        progress_queue: Queue for SSE progress events.

    Returns:
        MediaResult with final video path and metadata.
    """
    media_dir = output_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    chapters = state.chapters_written
    if options.chapters:
        chapters = [ch for ch in chapters if ch.chapter in options.chapters]

    if not chapters:
        raise ValueError("No chapters to process")

    total = len(chapters)
    chapter_videos: list[Path] = []
    chapter_results: list[ChapterVideoResult] = []

    def _emit(event: dict):
        try:
            progress_queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    for idx, ch in enumerate(chapters):
        ch_num = ch.chapter
        _emit({
            "type": "media_phase",
            "phase": "tts",
            "chapter": ch_num,
            "progress": idx / total,
            "message": f"{ch_num}장 음성 생성 중... ({idx + 1}/{total})",
        })

        # 1. TTS
        audio_path, vtt_path, duration = await generate_chapter_audio(
            chapter_num=ch_num,
            text=ch.content,
            voice=options.voice,
            output_dir=media_dir,
        )

        # Get accurate duration
        duration = await get_audio_duration(audio_path)

        _emit({
            "type": "media_phase",
            "phase": "subtitle",
            "chapter": ch_num,
            "message": f"{ch_num}장 자막 생성 중...",
        })

        # 2. VTT → ASS
        ass_path = media_dir / f"chapter_{ch_num:02d}.ass"
        vtt_to_ass(
            vtt_path=vtt_path,
            ass_path=ass_path,
            font_size=options.subtitle_font_size,
        )

        # 3. Title card (optional)
        if options.include_title_cards:
            title_path = media_dir / f"title_{ch_num:02d}.mp4"
            await generate_title_card_video(
                chapter_num=ch_num,
                title=ch.summary or f"제 {ch_num}장",
                duration=TITLE_CARD_DURATION,
                output_path=title_path,
                background_color=options.background_color,
            )
            chapter_videos.append(title_path)

        _emit({
            "type": "media_phase",
            "phase": "video",
            "chapter": ch_num,
            "progress": (idx + 0.5) / total,
            "message": f"{ch_num}장 영상 합성 중...",
        })

        # 4. Chapter video
        ch_video_path = media_dir / f"chapter_{ch_num:02d}.mp4"
        await compose_chapter_video(
            audio_path=audio_path,
            subtitle_path=ass_path,
            output_path=ch_video_path,
            background_color=options.background_color,
        )

        chapter_videos.append(ch_video_path)
        chapter_results.append(ChapterVideoResult(
            chapter=ch_num,
            video_path=str(ch_video_path),
            duration_seconds=duration,
        ))

        _emit({
            "type": "media_chapter_complete",
            "chapter": ch_num,
            "duration": round(duration, 1),
            "progress": (idx + 1) / total,
        })

    # 5. Concatenate all
    _emit({
        "type": "media_phase",
        "phase": "concatenating",
        "message": "전체 영상 합치는 중...",
    })

    final_path = output_dir / "novel_video.mp4"
    await concatenate_videos(
        video_paths=chapter_videos,
        output_path=final_path,
    )

    file_size = final_path.stat().st_size
    total_duration = sum(r.duration_seconds for r in chapter_results)
    if options.include_title_cards:
        total_duration += len(chapters) * TITLE_CARD_DURATION

    # Cleanup intermediate files (keep final video + per-chapter audio/video)
    for f in media_dir.glob("title_*.mp4"):
        f.unlink(missing_ok=True)
    for f in media_dir.glob("concat_list.txt"):
        f.unlink(missing_ok=True)

    # Sync media files to persistent storage (GCS)
    _emit({"type": "media_phase", "phase": "uploading", "message": "파일 저장 중..."})
    try:
        project_id = output_dir.name if output_dir.name != "output" else output_dir.parent.name
        # Upload final video
        storage_backend.write_binary(f"{project_id}/output/novel_video.mp4", final_path)
        # Upload per-chapter files
        for cr in chapter_results:
            ch_num = cr.chapter
            ch_video = media_dir / f"chapter_{ch_num:02d}.mp4"
            ch_audio = media_dir / f"chapter_{ch_num:02d}.mp3"
            if ch_video.exists():
                storage_backend.write_binary(f"{project_id}/output/media/chapter_{ch_num:02d}.mp4", ch_video)
            if ch_audio.exists():
                storage_backend.write_binary(f"{project_id}/output/media/chapter_{ch_num:02d}.mp3", ch_audio)
    except Exception as e:
        logger.warning("Failed to sync media to storage backend: %s", e)

    result = MediaResult(
        video_path=str(final_path),
        duration_seconds=total_duration,
        file_size_bytes=file_size,
        chapter_results=chapter_results,
    )

    _emit({
        "type": "media_done",
        "duration": round(total_duration, 1),
        "file_size_mb": round(file_size / (1024 * 1024), 1),
        "chapters_processed": len(chapter_results),
    })

    logger.info(
        "Media pipeline complete: %s (%.1fs, %.1fMB, %d chapters)",
        final_path, total_duration, file_size / (1024 * 1024), len(chapter_results),
    )

    return result
