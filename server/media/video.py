"""Video composition — ffmpeg-based chapter and full novel video generation.

Uses asyncio.subprocess for non-blocking ffmpeg calls with progress tracking.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE_BIN = shutil.which("ffprobe") or "ffprobe"

# Cache subtitle filter availability
_subtitle_filter_available: bool | None = None


async def _check_subtitle_support() -> bool:
    """Check if ffmpeg has ass/subtitles filter support."""
    global _subtitle_filter_available
    if _subtitle_filter_available is not None:
        return _subtitle_filter_available

    proc = await asyncio.create_subprocess_exec(
        FFMPEG_BIN, "-filters",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    output = stdout.decode("utf-8", errors="replace")
    _subtitle_filter_available = "ass" in output or "subtitles" in output
    logger.info("Subtitle filter available: %s", _subtitle_filter_available)
    return _subtitle_filter_available


async def get_audio_duration(audio_path: Path) -> float:
    """Get accurate audio duration using ffprobe."""
    proc = await asyncio.create_subprocess_exec(
        FFPROBE_BIN,
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(audio_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    try:
        return float(stdout.decode().strip())
    except (ValueError, IndexError):
        # Fallback: estimate from file size (MP3 ~128kbps)
        return audio_path.stat().st_size / (128 * 1000 / 8)


def _hex_to_ffmpeg_color(hex_color: str) -> str:
    """Convert #RRGGBB to ffmpeg-compatible 0xRRGGBB."""
    return "0x" + hex_color.lstrip("#")


async def _run_ffmpeg(
    args: list[str],
    total_duration: float | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> None:
    """Run ffmpeg with optional progress tracking.

    Parses stderr for time= to report progress percentage.
    """
    cmd = [FFMPEG_BIN, "-y"] + args

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stderr_data = b""
    while True:
        chunk = await proc.stderr.read(256)
        if not chunk:
            break
        stderr_data += chunk

        if on_progress and total_duration and total_duration > 0:
            text = chunk.decode("utf-8", errors="replace")
            match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", text)
            if match:
                h, m, s = match.groups()
                current = int(h) * 3600 + int(m) * 60 + float(s)
                pct = min(current / total_duration, 1.0)
                on_progress(pct)

    await proc.wait()

    if proc.returncode != 0:
        error_text = stderr_data.decode("utf-8", errors="replace")[-500:]
        raise RuntimeError(f"ffmpeg failed (code {proc.returncode}): {error_text}")


async def generate_title_card_video(
    chapter_num: int,
    title: str,
    duration: float,
    output_path: Path,
    background_color: str = "#1a1a2e",
    font_file: str | None = None,
) -> Path:
    """Generate a title card video clip.

    Uses drawtext if available, otherwise generates a plain color card.
    """
    color = _hex_to_ffmpeg_color(background_color)

    # Check if drawtext is available
    proc = await asyncio.create_subprocess_exec(
        FFMPEG_BIN, "-filters",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    has_drawtext = "drawtext" in stdout.decode("utf-8", errors="replace")

    if has_drawtext:
        font_opt = f":fontfile={font_file}" if font_file else ""
        chapter_text = f"{chapter_num}장"
        title_escaped = title.replace("'", "'\\''").replace(":", "\\:")

        filter_complex = (
            f"color=c={color}:s=1920x1080:d={duration},"
            f"drawtext=text='{chapter_text}'"
            f":fontsize=72{font_opt}"
            f":fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2-50"
            f":alpha='if(lt(t,1),t,if(gt(t,{duration - 1}),{duration}-t,1))',"
            f"drawtext=text='{title_escaped}'"
            f":fontsize=36{font_opt}"
            f":fontcolor=0xcccccc:x=(w-text_w)/2:y=(h-text_h)/2+50"
            f":alpha='if(lt(t,1),t,if(gt(t,{duration - 1}),{duration}-t,1))'"
        )

        args = [
            "-f", "lavfi",
            "-i", filter_complex,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-t", str(duration),
            str(output_path),
        ]
    else:
        # Fallback: plain color card without text
        logger.warning("drawtext not available — title card will be plain background")
        args = [
            "-f", "lavfi",
            "-i", f"color=c={color}:s=1920x1080:d={duration}:r=1",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-t", str(duration),
            str(output_path),
        ]

    await _run_ffmpeg(args)
    logger.info("Title card: %s (%.1fs)", output_path, duration)
    return output_path


async def compose_chapter_video(
    audio_path: Path,
    subtitle_path: Path | None,
    output_path: Path,
    background_color: str = "#1a1a2e",
    background_image: Path | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """Compose a chapter video: background + audio + subtitles.

    Args:
        audio_path: MP3 audio file.
        subtitle_path: ASS subtitle file (optional).
        output_path: Output MP4 path.
        background_color: Hex color for background (used if no image).
        background_image: Optional background image path.
        on_progress: Progress callback (0.0 to 1.0).
    """
    duration = await get_audio_duration(audio_path)
    color = _hex_to_ffmpeg_color(background_color)

    args: list[str] = []

    if background_image and background_image.exists():
        # Use image as background, looped to audio duration
        args += [
            "-loop", "1",
            "-i", str(background_image),
        ]
    else:
        # Generate solid color background
        args += [
            "-f", "lavfi",
            "-i", f"color=c={color}:s=1920x1080:d={duration}",
        ]

    # Add audio input
    args += ["-i", str(audio_path)]

    # Video filter: scale + subtitle overlay (if supported)
    vf_parts: list[str] = []
    if background_image and background_image.exists():
        vf_parts.append("scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2")

    has_sub_filter = await _check_subtitle_support()
    if subtitle_path and subtitle_path.exists() and has_sub_filter:
        sub_str = str(subtitle_path).replace("\\", "/").replace(":", "\\:")
        vf_parts.append(f"ass={sub_str}")
    elif subtitle_path and subtitle_path.exists():
        logger.warning("Subtitle filter not available — video will be without subtitles")

    if vf_parts:
        args += ["-vf", ",".join(vf_parts)]

    args += [
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        str(output_path),
    ]

    await _run_ffmpeg(args, total_duration=duration, on_progress=on_progress)
    logger.info("Chapter video: %s (%.1fs)", output_path, duration)
    return output_path


async def concatenate_videos(
    video_paths: list[Path],
    output_path: Path,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """Concatenate multiple video files into one using ffmpeg concat demuxer.

    Args:
        video_paths: Ordered list of MP4 files.
        output_path: Final output MP4 path.
        on_progress: Progress callback.
    """
    if len(video_paths) == 1:
        # Just copy the single file
        shutil.copy2(video_paths[0], output_path)
        return output_path

    # Create concat file list
    concat_list = output_path.parent / "concat_list.txt"
    lines = [f"file '{p.resolve()}'" for p in video_paths]
    concat_list.write_text("\n".join(lines), encoding="utf-8")

    # Get total duration for progress
    total_dur = 0.0
    for vp in video_paths:
        total_dur += await get_audio_duration(vp)

    args = [
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]

    await _run_ffmpeg(args, total_duration=total_dur, on_progress=on_progress)

    # Cleanup concat list
    concat_list.unlink(missing_ok=True)

    logger.info(
        "Concatenated %d videos: %s (%.1fs)",
        len(video_paths), output_path, total_dur,
    )
    return output_path
