"""Context Builder — prevents context window explosion.

Constructs an optimised context payload for the Writer agent by:
1. Filtering only characters involved in the current chapter.
2. Using a sliding window of recent chapter summaries (last 2).
3. Compressing older chapters into a single-line synopsis.
4. Including only unresolved foreshadowing elements.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import (
    Character,
    ChapterOutline,
    ChapterResult,
    Foreshadowing,
    NovelState,
)


@dataclass
class WriterContext:
    """Optimised context payload delivered to the Writer agent."""

    chapter_goal: ChapterOutline
    characters: list[Character]
    recent_chapters: list[ChapterResult]
    older_summary: str
    ending_hook: str
    open_foreshadowing: list[Foreshadowing]
    world_tone: str
    world_rules: list[str]

    def to_prompt_text(self) -> str:
        """Serialize the context into a prompt-friendly text block."""
        parts: list[str] = []

        # World setting
        parts.append(f"## 세계관\n- 톤: {self.world_tone}")
        if self.world_rules:
            parts.append("- 규칙:\n" + "\n".join(f"  - {r}" for r in self.world_rules))

        # Characters
        parts.append("\n## 등장인물")
        for ch in self.characters:
            inv = ", ".join(ch.inventory) if ch.inventory else "없음"
            rels = ", ".join(f"{k}({v})" for k, v in ch.relationships.items()) if ch.relationships else "없음"
            parts.append(
                f"- **{ch.name}** | 상태: {ch.status} | 위치: {ch.location}\n"
                f"  성격: {ch.traits}\n"
                f"  소지품: {inv}\n"
                f"  관계: {rels}"
            )

        # Story so far (compressed)
        if self.older_summary:
            parts.append(f"\n## 이전 줄거리 요약\n{self.older_summary}")

        # Recent chapters (detailed)
        if self.recent_chapters:
            parts.append("\n## 최근 장 상세")
            for ch in self.recent_chapters:
                parts.append(f"### {ch.chapter}장 (요약: {ch.summary})")
                # Include last 500 chars for continuity
                tail = ch.content[-500:] if len(ch.content) > 500 else ch.content
                parts.append(f"(마지막 부분)\n{tail}")

        # Ending hook
        if self.ending_hook:
            parts.append(f"\n## 이전 장 마지막 장면\n{self.ending_hook}")

        # Current chapter goal
        parts.append(f"\n## 이번 장 목표 ({self.chapter_goal.chapter}장)")
        parts.append(f"- 목표: {self.chapter_goal.goal}")
        parts.append(f"- 시점: {self.chapter_goal.pov_character}")
        if self.chapter_goal.key_events:
            parts.append("- 핵심 이벤트:\n" + "\n".join(f"  - {e}" for e in self.chapter_goal.key_events))

        # Open foreshadowing
        if self.open_foreshadowing:
            parts.append("\n## 미해결 복선")
            for f in self.open_foreshadowing:
                parts.append(f"- [{f.id}] ({f.planted_chapter}장에서 심음) {f.description}")

        return "\n".join(parts)


def build_writer_context(state: NovelState) -> WriterContext:
    """Build an optimised context from the current novel state."""

    outline = state.get_current_outline()
    if outline is None:
        raise ValueError(f"No outline found for chapter {state.current_chapter}")

    # 1. Filter characters involved in this chapter
    involved_names = {n.lower() for n in outline.involved_characters}
    # Always include POV character
    involved_names.add(outline.pov_character.lower())

    relevant_chars = [
        ch for ch in state.characters
        if ch.name.lower() in involved_names
    ]
    # Fallback: if filtering is too aggressive, include all alive chars
    if not relevant_chars:
        relevant_chars = [ch for ch in state.characters if ch.status == "alive"]

    # 2. Sliding window: last 2 chapters in detail
    recent = state.chapters_written[-2:] if state.chapters_written else []

    # 3. Compress older chapters
    older = state.chapters_written[:-2] if len(state.chapters_written) > 2 else []
    older_summary = ""
    if older:
        older_summary = " → ".join(ch.summary for ch in older)

    # 4. Ending hook from the most recent chapter
    ending_hook = ""
    if state.chapters_written:
        last = state.chapters_written[-1]
        ending_hook = last.ending_hook or last.content[-300:]

    # 5. Open foreshadowing
    open_fs = state.get_open_foreshadowing()

    return WriterContext(
        chapter_goal=outline,
        characters=relevant_chars,
        recent_chapters=recent,
        older_summary=older_summary,
        ending_hook=ending_hook,
        open_foreshadowing=open_fs,
        world_tone=state.world_setting.tone,
        world_rules=state.world_setting.rules,
    )
