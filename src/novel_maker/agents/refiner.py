"""Refiner Agent — fixes issues identified by the Checker.

Receives the draft plus structured error feedback and produces
a corrected version while preserving the overall narrative flow.
"""

from __future__ import annotations

import logging

from google import genai

from ..models import CheckResult, NovelState
from ..prompts import REFINER_SYSTEM, refiner_prompt
from ..token_tracker import TokenTracker
from ..utils import gemini_retry

logger = logging.getLogger(__name__)


def _format_errors(result: CheckResult) -> str:
    """Convert checker errors to a readable list for the refiner."""
    if not result.errors:
        return "오류 없음"

    lines: list[str] = []
    for i, err in enumerate(result.errors, 1):
        severity_icon = "🔴" if err.severity == "critical" else "🟡"
        lines.append(f"{i}. {severity_icon} [{err.code}] {err.description}")
    return "\n".join(lines)


def _format_revision_history(state: NovelState) -> str:
    """Include full revision history so the refiner avoids repeating mistakes."""
    if not state.revision_history:
        return ""

    lines: list[str] = []
    for i, prev_result in enumerate(state.revision_history, 1):
        if prev_result.errors:
            for err in prev_result.errors:
                lines.append(f"- Rev {i}: [{err.code}] {err.description}")
    return "\n".join(lines)


@gemini_retry()
async def refine_chapter(
    client: genai.Client,
    state: NovelState,
    draft: str,
    check_result: CheckResult,
    model: str = "gemini-2.5-flash",
    tracker: TokenTracker | None = None,
) -> str:
    """Refine a chapter draft based on checker feedback.

    Returns the corrected chapter text.
    """
    chapter_num = state.current_chapter
    revision = state.revision_count + 1
    logger.info("Refining chapter %d (revision %d)", chapter_num, revision)

    errors_text = _format_errors(check_result)
    revision_history = _format_revision_history(state)

    user_msg = refiner_prompt(
        draft=draft,
        errors_text=errors_text,
        revision_history=revision_history,
    )

    response = await client.aio.models.generate_content(
        model=model,
        contents=user_msg,
        config=genai.types.GenerateContentConfig(
            system_instruction=REFINER_SYSTEM,
            temperature=0.7,
            max_output_tokens=8192,
        ),
    )

    # Track tokens
    if tracker and response.usage_metadata:
        tracker.record(
            agent="refiner",
            chapter=chapter_num,
            input_tokens=response.usage_metadata.prompt_token_count or 0,
            output_tokens=response.usage_metadata.candidates_token_count or 0,
        )

    refined = response.text.strip()
    logger.info(
        "Chapter %d refined (rev %d): %d chars",
        chapter_num, revision, len(refined),
    )
    return refined
