"""Planner Agent — generates the complete novel blueprint from a logline.

Takes a one-line story idea and produces a full NovelState including
world setting, characters, chapter outlines, and foreshadowing.
"""

from __future__ import annotations

import logging

from google import genai
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import (
    Character,
    ChapterOutline,
    Foreshadowing,
    NovelState,
    WorldSetting,
)
from ..prompts import PLANNER_SYSTEM, planner_prompt
from ..token_tracker import TokenTracker
from ..utils import parse_json_response

logger = logging.getLogger(__name__)


@retry(
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def plan_novel(
    client: genai.Client,
    logline: str,
    total_chapters: int = 3,
    language: str = "ko",
    model: str = "gemini-2.5-flash",
    tracker: TokenTracker | None = None,
) -> NovelState:
    """Generate the full novel plan from a logline.

    Returns a fully populated NovelState ready for the writing loop.
    """
    logger.info("Planning novel: '%s' (%d chapters)", logline, total_chapters)

    user_msg = planner_prompt(logline, total_chapters, language)

    response = await client.aio.models.generate_content(
        model=model,
        contents=user_msg,
        config=genai.types.GenerateContentConfig(
            system_instruction=PLANNER_SYSTEM,
            response_mime_type="application/json",
            temperature=0.8,
        ),
    )

    # Track tokens
    if tracker and response.usage_metadata:
        tracker.record(
            agent="planner",
            chapter=0,
            input_tokens=response.usage_metadata.prompt_token_count or 0,
            output_tokens=response.usage_metadata.candidates_token_count or 0,
        )

    # Parse the JSON response
    data = parse_json_response(response.text)

    # Build NovelState from parsed data
    world = WorldSetting.model_validate(data.get("world_setting", {}))

    characters = [
        Character.model_validate(ch)
        for ch in data.get("characters", [])
    ]

    outlines = [
        ChapterOutline.model_validate(ol)
        for ol in data.get("plot_outline", [])
    ]

    foreshadowing = [
        Foreshadowing.model_validate(fs)
        for fs in data.get("foreshadowing", [])
    ]

    state = NovelState(
        world_setting=world,
        characters=characters,
        plot_outline=outlines,
        foreshadowing=foreshadowing,
        current_chapter=1,
        total_chapters=total_chapters,
    )

    logger.info(
        "Plan created: %d characters, %d chapters, %d foreshadowing",
        len(characters), len(outlines), len(foreshadowing),
    )
    return state
