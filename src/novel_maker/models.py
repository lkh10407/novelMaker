"""Pydantic data models for novel state management.

All novel data flows through these type-safe models, ensuring
consistency between agents and preventing invalid state transitions.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# World & Character models
# ---------------------------------------------------------------------------

class Character(BaseModel):
    """A character in the novel with tracked state."""

    id: int
    name: str
    traits: str = Field(description="성격/특성 요약")
    status: Literal["alive", "dead", "missing"] = "alive"
    location: str = ""
    inventory: list[str] = Field(default_factory=list)
    relationships: dict[str, str] = Field(
        default_factory=dict,
        description="캐릭터명 → 관계 (예: {'영희': '연인'})",
    )


class WorldSetting(BaseModel):
    """Global world-building rules and tone."""

    tone: str = Field(default="", description="분위기 (다크, 코믹, 서정적 등)")
    rules: list[str] = Field(
        default_factory=list,
        description="세계관 핵심 규칙",
    )
    locations: list[str] = Field(default_factory=list)
    time_period: str = Field(default="", description="시대/배경 시간")


# ---------------------------------------------------------------------------
# Plot outline
# ---------------------------------------------------------------------------

class ChapterOutline(BaseModel):
    """Plan for a single chapter."""

    chapter: int
    goal: str
    key_events: list[str] = Field(default_factory=list)
    pov_character: str = Field(description="시점 캐릭터")
    involved_characters: list[str] = Field(
        default_factory=list,
        description="이 장에 등장하는 캐릭터 이름 목록",
    )


# ---------------------------------------------------------------------------
# Foreshadowing (복선/떡밥)
# ---------------------------------------------------------------------------

class Foreshadowing(BaseModel):
    """A foreshadowing element to plant and later resolve."""

    id: int
    planted_chapter: int
    description: str
    resolved: bool = False
    resolved_chapter: int | None = None


# ---------------------------------------------------------------------------
# Checker result models
# ---------------------------------------------------------------------------

ErrorCode = Literal[
    "ERR_DEAD_CHAR",
    "ERR_MISSING_ITEM",
    "ERR_CHAR_BREAK",
    "ERR_LOCATION",
    "ERR_STYLE_BREAK",
    "ERR_PLOT_HOLE",
    "ERR_OTHER",
]


class CheckerError(BaseModel):
    """A single error found by the consistency checker."""

    code: ErrorCode
    description: str
    severity: Literal["critical", "warning"] = "critical"


class CheckResult(BaseModel):
    """Aggregated result from the checker agent."""

    passed: bool
    errors: list[CheckerError] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Chapter result
# ---------------------------------------------------------------------------

class ChapterResult(BaseModel):
    """Output of a completed (and approved) chapter."""

    chapter: int
    content: str
    summary: str = Field(description="이 장의 한 줄 요약")
    ending_hook: str = Field(
        default="",
        description="다음 장으로 이어지는 마지막 장면/문장",
    )
    state_changes: list[str] = Field(
        default_factory=list,
        description="이 장에서 일어난 상태 변화 목록",
    )
    char_count: int = 0


# ---------------------------------------------------------------------------
# Central novel state (LangGraph state object)
# ---------------------------------------------------------------------------

class NovelState(BaseModel):
    """Central state shared across all LangGraph nodes.

    Every agent reads from and writes to this state, ensuring
    a single source of truth for the entire novel.
    """

    # -- World & characters --
    world_setting: WorldSetting = Field(default_factory=WorldSetting)
    characters: list[Character] = Field(default_factory=list)

    # -- Plot --
    plot_outline: list[ChapterOutline] = Field(default_factory=list)
    foreshadowing: list[Foreshadowing] = Field(default_factory=list)

    # -- Progress --
    chapters_written: list[ChapterResult] = Field(default_factory=list)
    current_chapter: int = 1
    total_chapters: int = 3
    current_draft: str = ""

    # -- Revision loop --
    revision_count: int = 0
    max_revisions: int = 3
    revision_history: list[CheckResult] = Field(default_factory=list)
    checker_result: CheckResult | None = None

    # -- Token tracking --
    token_usage: dict[str, dict[str, int]] = Field(default_factory=dict)
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    # -- Workflow control --
    phase: Literal[
        "planning",
        "writing",
        "checking",
        "refining",
        "updating",
        "replanning",
        "done",
    ] = "planning"
    error_message: str = ""

    def get_character_by_name(self, name: str) -> Character | None:
        """Look up a character by name (case-insensitive)."""
        for ch in self.characters:
            if ch.name.lower() == name.lower():
                return ch
        return None

    def get_current_outline(self) -> ChapterOutline | None:
        """Return the outline for the current chapter."""
        for outline in self.plot_outline:
            if outline.chapter == self.current_chapter:
                return outline
        return None

    def get_open_foreshadowing(self) -> list[Foreshadowing]:
        """Return all unresolved foreshadowing elements."""
        return [f for f in self.foreshadowing if not f.resolved]
