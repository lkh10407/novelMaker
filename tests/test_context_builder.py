"""Tests for novel_maker.context_builder."""

import pytest

from novel_maker.models import (
    Character,
    ChapterOutline,
    ChapterResult,
    Foreshadowing,
    NovelState,
    WorldSetting,
)
from novel_maker.context_builder import build_writer_context, WriterContext


def _make_state(
    current_chapter: int = 1,
    num_characters: int = 3,
    num_chapters_written: int = 0,
) -> NovelState:
    """Helper to build a test NovelState."""
    characters = [
        Character(
            id=i + 1,
            name=f"캐릭터{i + 1}",
            traits=f"특성{i + 1}",
            location=f"장소{i + 1}",
        )
        for i in range(num_characters)
    ]

    outlines = [
        ChapterOutline(
            chapter=j + 1,
            goal=f"목표{j + 1}",
            key_events=[f"이벤트{j + 1}"],
            pov_character="캐릭터1",
            involved_characters=["캐릭터1", "캐릭터2"],
        )
        for j in range(max(current_chapter, 3))
    ]

    chapters_written = [
        ChapterResult(
            chapter=k + 1,
            content=f"챕터{k + 1} 내용입니다. " * 50,
            summary=f"챕터{k + 1} 요약",
            ending_hook=f"챕터{k + 1} 훅",
            char_count=500,
        )
        for k in range(num_chapters_written)
    ]

    foreshadowing = [
        Foreshadowing(id=1, planted_chapter=1, description="복선1"),
        Foreshadowing(id=2, planted_chapter=1, description="복선2", resolved=True, resolved_chapter=2),
    ]

    return NovelState(
        world_setting=WorldSetting(
            tone="다크",
            rules=["규칙1", "규칙2"],
            locations=["도시", "숲"],
            time_period="현대",
        ),
        characters=characters,
        plot_outline=outlines,
        foreshadowing=foreshadowing,
        chapters_written=chapters_written,
        current_chapter=current_chapter,
        total_chapters=len(outlines),
    )


class TestBuildWriterContext:
    def test_basic_context_build(self):
        state = _make_state(current_chapter=1)
        ctx = build_writer_context(state)
        assert isinstance(ctx, WriterContext)
        assert ctx.chapter_goal.chapter == 1
        assert ctx.world_tone == "다크"

    def test_filters_involved_characters(self):
        state = _make_state(current_chapter=1, num_characters=5)
        ctx = build_writer_context(state)
        # outline says involved = 캐릭터1, 캐릭터2
        names = {ch.name for ch in ctx.characters}
        assert "캐릭터1" in names
        assert "캐릭터2" in names

    def test_recent_chapters_sliding_window(self):
        state = _make_state(current_chapter=4, num_chapters_written=3)
        # Ensure outline exists for chapter 4
        state.plot_outline.append(
            ChapterOutline(
                chapter=4, goal="목표4", pov_character="캐릭터1",
                involved_characters=["캐릭터1"],
            )
        )
        ctx = build_writer_context(state)
        # Should have last 2 chapters (2, 3)
        assert len(ctx.recent_chapters) == 2
        assert ctx.recent_chapters[0].chapter == 2
        assert ctx.recent_chapters[1].chapter == 3

    def test_older_summary_compression(self):
        state = _make_state(current_chapter=4, num_chapters_written=3)
        state.plot_outline.append(
            ChapterOutline(
                chapter=4, goal="목표4", pov_character="캐릭터1",
                involved_characters=["캐릭터1"],
            )
        )
        ctx = build_writer_context(state)
        # Chapter 1 should be compressed into older_summary
        assert "챕터1 요약" in ctx.older_summary

    def test_open_foreshadowing_only(self):
        state = _make_state(current_chapter=1)
        ctx = build_writer_context(state)
        # Only unresolved foreshadowing
        assert len(ctx.open_foreshadowing) == 1
        assert ctx.open_foreshadowing[0].description == "복선1"

    def test_ending_hook_from_last_chapter(self):
        state = _make_state(current_chapter=2, num_chapters_written=1)
        ctx = build_writer_context(state)
        assert ctx.ending_hook == "챕터1 훅"

    def test_no_outline_raises(self):
        state = _make_state(current_chapter=1)
        state.plot_outline = []  # remove all outlines
        with pytest.raises(ValueError, match="No outline found"):
            build_writer_context(state)

    def test_to_prompt_text_contains_sections(self):
        state = _make_state(current_chapter=2, num_chapters_written=1)
        ctx = build_writer_context(state)
        text = ctx.to_prompt_text()
        assert "## 세계관" in text
        assert "## 등장인물" in text
        assert "## 이번 장 목표" in text
        assert "다크" in text

    def test_fallback_to_all_alive_characters(self):
        """If no characters match involved list, fall back to all alive."""
        state = _make_state(current_chapter=1, num_characters=3)
        # Clear involved characters to trigger fallback
        state.plot_outline[0].involved_characters = ["존재하지않는캐릭터"]
        state.plot_outline[0].pov_character = "존재하지않는POV"
        ctx = build_writer_context(state)
        assert len(ctx.characters) == 3  # all alive
