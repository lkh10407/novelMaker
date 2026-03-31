"""Pydantic models for the media generation pipeline."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class MediaGenerateRequest(BaseModel):
    """Request body for starting media generation."""

    voice: str = Field(
        default="ko-KR-SunHiNeural",
        description="edge-tts voice name",
    )
    background_color: str = Field(
        default="#1a1a2e",
        description="Hex background color",
    )
    background_image_url: str | None = Field(
        default=None,
        description="Optional background image URL",
    )
    subtitle_font_size: int = Field(default=28, ge=12, le=72)
    subtitle_color: str = Field(default="#FFFFFF")
    include_title_cards: bool = True
    chapters: list[int] | None = Field(
        default=None,
        description="Specific chapters to generate (None = all)",
    )


KOREAN_VOICES = {
    "ko-KR-SunHiNeural": "선희 (여성)",
    "ko-KR-InJoonNeural": "인준 (남성)",
    "ko-KR-HyunsuMultilingualNeural": "현수 (남성, 다국어)",
}


class TTSResult(BaseModel):
    """Result of TTS generation for a single chapter."""

    chapter: int
    audio_path: str
    subtitle_path: str
    duration_seconds: float


class ChapterVideoResult(BaseModel):
    """Result of video generation for a single chapter."""

    chapter: int
    video_path: str
    duration_seconds: float


class MediaResult(BaseModel):
    """Final result of the full media pipeline."""

    video_path: str
    duration_seconds: float
    file_size_bytes: int
    chapter_results: list[ChapterVideoResult] = Field(default_factory=list)
