"""Checker Agent — validates a draft chapter against the novel state.

Performs a 6-point consistency check and returns structured errors
with error codes for tracking across revisions.
"""

from __future__ import annotations

import json
import logging

from google import genai
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import CheckResult, CheckerError, NovelState
from ..prompts import CHECKER_SYSTEM, checker_prompt
from ..token_tracker import TokenTracker
from ..utils import parse_json_response

logger = logging.getLogger(__name__)


def _format_revision_history(state: NovelState) -> str:
    """Format previous revision errors for the checker prompt."""
    if not state.revision_history:
        return ""

    lines: list[str] = []
    for i, result in enumerate(state.revision_history, 1):
        if result.errors:
            errors_str = "; ".join(
                f"{e.code}: {e.description}" for e in result.errors
            )
            lines.append(f"- Rev {i}: {errors_str}")

    return "\n".join(lines)


@retry(
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def check_chapter(
    client: genai.Client,
    state: NovelState,
    draft: str,
    model: str = "gemini-2.5-flash",
    tracker: TokenTracker | None = None,
) -> CheckResult:
    """Check a chapter draft for consistency errors.

    Returns a CheckResult with passed=True/False and a list of errors.
    """
    chapter_num = state.current_chapter
    logger.info("Checking chapter %d (revision %d)", chapter_num, state.revision_count)

    # Serialize state data for the checker
    chars_json = json.dumps(
        [ch.model_dump() for ch in state.characters],
        ensure_ascii=False, indent=2,
    )
    world_json = json.dumps(
        state.world_setting.model_dump(),
        ensure_ascii=False, indent=2,
    )
    fs_json = json.dumps(
        [f.model_dump() for f in state.get_open_foreshadowing()],
        ensure_ascii=False, indent=2,
    )
    revision_history = _format_revision_history(state)

    user_msg = checker_prompt(
        draft=draft,
        characters_json=chars_json,
        world_json=world_json,
        foreshadowing_json=fs_json,
        revision_history=revision_history,
    )

    response = await client.aio.models.generate_content(
        model=model,
        contents=user_msg,
        config=genai.types.GenerateContentConfig(
            system_instruction=CHECKER_SYSTEM,
            response_mime_type="application/json",
            temperature=0.3,  # Lower temperature for analytical task
        ),
    )

    # Track tokens
    if tracker and response.usage_metadata:
        tracker.record(
            agent="checker",
            chapter=chapter_num,
            input_tokens=response.usage_metadata.prompt_token_count or 0,
            output_tokens=response.usage_metadata.candidates_token_count or 0,
        )

    # Parse structured response
    data = parse_json_response(response.text)

    # Build CheckResult
    errors = []
    for err_data in data.get("errors", []):
        try:
            errors.append(CheckerError.model_validate(err_data))
        except Exception:
            # Fallback for unexpected error format
            errors.append(CheckerError(
                code="ERR_OTHER",
                description=str(err_data),
                severity="warning",
            ))

    result = CheckResult(
        passed=data.get("passed", len(errors) == 0),
        errors=errors,
    )

    # Check for repeated errors (same error code 3+ times across revisions)
    if not result.passed and state.revision_count >= 2:
        current_codes = {e.code for e in result.errors}
        all_prev_codes: dict[str, int] = {}
        for prev_result in state.revision_history:
            for e in prev_result.errors:
                all_prev_codes[e.code] = all_prev_codes.get(e.code, 0) + 1

        stuck_codes = [
            code for code in current_codes
            if all_prev_codes.get(code, 0) >= 2
        ]
        if stuck_codes:
            logger.warning(
                "Repeated errors detected (3+ times): %s — forcing PASS",
                stuck_codes,
            )
            result.passed = True
            for e in result.errors:
                if e.code in stuck_codes:
                    e.severity = "warning"

    status = "PASS ✅" if result.passed else f"REJECT ❌ ({len(result.errors)} errors)"
    logger.info("Chapter %d check: %s", chapter_num, status)

    return result
