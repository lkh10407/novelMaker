"""Subtitle generation — converts VTT timing data to ASS format.

ASS (Advanced SubStation Alpha) provides styled subtitles with
custom fonts, colors, and positioning for video overlay.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def _parse_vtt_time(time_str: str) -> float:
    """Convert VTT timestamp (HH:MM:SS.mmm) to seconds."""
    parts = time_str.strip().replace(",", ".").split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(parts[0])


def _seconds_to_ass_time(seconds: float) -> str:
    """Convert seconds to ASS timestamp (H:MM:SS.cc)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def vtt_to_srt(vtt_path: Path, srt_path: Path) -> Path:
    """Convert VTT subtitle file to SRT format."""
    vtt_text = vtt_path.read_text(encoding="utf-8")

    # Remove VTT header
    vtt_text = re.sub(r"^WEBVTT\s*\n", "", vtt_text)
    vtt_text = re.sub(r"^Kind:.*\n", "", vtt_text, flags=re.MULTILINE)
    vtt_text = re.sub(r"^Language:.*\n", "", vtt_text, flags=re.MULTILINE)

    # Parse cues
    cues = re.findall(
        r"(\d[\d:,.]+)\s*-->\s*(\d[\d:,.]+)\s*\n(.+?)(?=\n\n|\Z)",
        vtt_text,
        re.DOTALL,
    )

    srt_lines: list[str] = []
    for i, (start, end, text) in enumerate(cues, 1):
        # Normalize timestamps for SRT (use comma instead of dot)
        start_srt = start.replace(".", ",")
        end_srt = end.replace(".", ",")
        srt_lines.append(f"{i}")
        srt_lines.append(f"{start_srt} --> {end_srt}")
        srt_lines.append(text.strip())
        srt_lines.append("")

    srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
    return srt_path


def vtt_to_ass(
    vtt_path: Path,
    ass_path: Path,
    font_name: str = "Noto Sans CJK KR",
    font_size: int = 28,
    primary_color: str = "&H00FFFFFF",
    outline_color: str = "&H00000000",
    back_color: str = "&H80000000",
    margin_v: int = 50,
) -> Path:
    """Convert VTT subtitle to ASS format with styling.

    Args:
        vtt_path: Input VTT file.
        ass_path: Output ASS file.
        font_name: Font face name.
        font_size: Font size.
        primary_color: Text color in ASS &HAABBGGRR format.
        outline_color: Outline color.
        back_color: Shadow/background color.
        margin_v: Vertical margin from bottom.
    """
    vtt_text = vtt_path.read_text(encoding="utf-8")

    # Parse VTT cues
    cues = re.findall(
        r"(\d[\d:,.]+)\s*-->\s*(\d[\d:,.]+)\s*\n(.+?)(?=\n\n|\Z)",
        vtt_text,
        re.DOTALL,
    )

    # ASS header
    ass_lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1920",
        "PlayResY: 1080",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font_name},{font_size},{primary_color},&H000000FF,"
        f"{outline_color},{back_color},-1,0,0,0,100,100,0,0,1,3,1,2,30,30,{margin_v},1",
        f"Style: Title,{font_name},{font_size + 16},{primary_color},&H000000FF,"
        f"{outline_color},{back_color},-1,0,0,0,100,100,0,0,1,4,2,5,30,30,30,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    # Convert cues to ASS dialogue lines
    for start_str, end_str, text in cues:
        start_sec = _parse_vtt_time(start_str)
        end_sec = _parse_vtt_time(end_str)
        ass_start = _seconds_to_ass_time(start_sec)
        ass_end = _seconds_to_ass_time(end_sec)
        clean_text = text.strip().replace("\n", "\\N")
        ass_lines.append(
            f"Dialogue: 0,{ass_start},{ass_end},Default,,0,0,0,,{clean_text}"
        )

    ass_path.write_text("\n".join(ass_lines), encoding="utf-8")
    logger.info("ASS subtitle generated: %s (%d cues)", ass_path, len(cues))
    return ass_path


def generate_title_card_ass(
    chapter_num: int,
    chapter_title: str,
    duration: float,
    ass_path: Path,
    font_name: str = "Noto Sans CJK KR",
    font_size: int = 48,
) -> Path:
    """Generate a standalone ASS file for a chapter title card."""
    end_time = _seconds_to_ass_time(duration)

    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,4,2,5,30,30,30,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,{end_time},Title,,0,0,0,,{{\\fad(500,500)}}{chapter_num}장\\N{chapter_title}
"""

    ass_path.write_text(ass_content, encoding="utf-8")
    return ass_path
