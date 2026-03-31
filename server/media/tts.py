"""TTS Engine — converts chapter text to speech using edge-tts.

Produces MP3 audio and word-level timing data for subtitle generation.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from pathlib import Path

import edge_tts

logger = logging.getLogger(__name__)

# Pause duration (ms) inserted between paragraphs
PARAGRAPH_PAUSE_MS = 800


def _clean_text_for_tts(text: str) -> str:
    """Strip markdown formatting and normalize for TTS."""
    # Remove markdown headers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove bold/italic markers
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    # Remove inline code
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Remove horizontal rules
    text = re.sub(r"^-{3,}$", "", text, flags=re.MULTILINE)
    # Collapse multiple newlines but preserve paragraph breaks
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip leading/trailing whitespace per line
    text = "\n".join(line.strip() for line in text.splitlines())
    return text.strip()


def _split_into_segments(text: str, max_chars: int = 2000) -> list[str]:
    """Split text into TTS-friendly segments at paragraph boundaries.

    edge-tts handles long text but splitting gives better timing data
    and allows progress tracking per segment.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    segments: list[str] = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 > max_chars and current:
            segments.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para

    if current:
        segments.append(current)

    return segments if segments else [text]


class TTSTimingEntry:
    """A single word/phrase with its timing offset."""

    __slots__ = ("text", "offset_ms", "duration_ms")

    def __init__(self, text: str, offset_ms: float, duration_ms: float):
        self.text = text
        self.offset_ms = offset_ms
        self.duration_ms = duration_ms


async def generate_chapter_audio(
    chapter_num: int,
    text: str,
    voice: str,
    output_dir: Path,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[Path, Path, float]:
    """Generate TTS audio and subtitle data for a chapter.

    Returns:
        (audio_path, vtt_subtitle_path, duration_seconds)
    """
    clean_text = _clean_text_for_tts(text)
    segments = _split_into_segments(clean_text)

    audio_path = output_dir / f"chapter_{chapter_num:02d}.mp3"
    vtt_path = output_dir / f"chapter_{chapter_num:02d}.vtt"

    if on_progress:
        on_progress(f"{chapter_num}장 TTS 시작 ({len(segments)}개 세그먼트)")

    # Use edge-tts SubMaker for word-level timing
    communicate = edge_tts.Communicate(clean_text, voice)
    submaker = edge_tts.SubMaker()

    # Generate audio with timing data
    with open(audio_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)

    # Write SRT subtitle (edge-tts provides SRT via get_srt)
    srt_content = submaker.get_srt()
    vtt_path.write_text(srt_content, encoding="utf-8")

    # Calculate duration from audio file size (MP3 ~128kbps)
    file_size = audio_path.stat().st_size
    duration = file_size / (128 * 1000 / 8)  # approximate

    if on_progress:
        on_progress(f"{chapter_num}장 TTS 완료 ({duration:.0f}초)")

    logger.info(
        "Chapter %d TTS: %s (%.1fs, %d bytes)",
        chapter_num, voice, duration, file_size,
    )

    return audio_path, vtt_path, duration
