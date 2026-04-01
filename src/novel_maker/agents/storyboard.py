"""Storyboard Agent — breaks chapter text into animation keyframe scenes.

Each scene includes a visual description, image generation prompt (English),
camera angle, characters, and mood for AI animation production.
"""

from __future__ import annotations

import json
import logging

from google import genai

from ..models import NovelState, StoryboardScene
from ..prompts import STORYBOARD_SYSTEM, storyboard_prompt
from ..token_tracker import TokenTracker
from ..utils import gemini_retry, parse_json_response

logger = logging.getLogger(__name__)


@gemini_retry()
async def generate_storyboard(
    client: genai.Client,
    state: NovelState,
    chapter_num: int,
    model: str = "gemini-2.5-flash",
    tracker: TokenTracker | None = None,
) -> list[StoryboardScene]:
    """Generate storyboard scenes for a specific chapter.

    Returns a list of StoryboardScene objects (8-12 per chapter).
    """
    # Find the chapter content
    chapter = None
    for ch in state.chapters_written:
        if ch.chapter == chapter_num:
            chapter = ch
            break

    if chapter is None:
        raise ValueError(f"Chapter {chapter_num} not found in state")

    chars_json = json.dumps(
        [c.model_dump() for c in state.characters],
        ensure_ascii=False,
        indent=2,
    )

    user_msg = storyboard_prompt(chapter_num, chapter.content, chars_json)

    response = await client.aio.models.generate_content(
        model=model,
        contents=user_msg,
        config=genai.types.GenerateContentConfig(
            system_instruction=STORYBOARD_SYSTEM,
            response_mime_type="application/json",
            temperature=0.7,
            max_output_tokens=8192,
        ),
    )

    if tracker and response.usage_metadata:
        tracker.record(
            agent="storyboard",
            chapter=chapter_num,
            input_tokens=response.usage_metadata.prompt_token_count or 0,
            output_tokens=response.usage_metadata.candidates_token_count or 0,
        )

    data = parse_json_response(response.text)

    # Handle both direct list and wrapped object
    scenes_list = data if isinstance(data, list) else data.get("storyboard", data.get("scenes", []))

    scenes = [StoryboardScene.model_validate(s) for s in scenes_list]
    logger.info("Chapter %d storyboard: %d scenes", chapter_num, len(scenes))
    return scenes
