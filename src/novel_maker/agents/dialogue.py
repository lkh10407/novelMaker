"""Dialogue Agent — generates narration and character dialogue per scene.

Takes chapter text + storyboard scenes and produces dialogue lines
aligned to each scene, with speaker, emotion, and direction.
"""

from __future__ import annotations

import json
import logging

from google import genai

from ..models import DialogueLine, NovelState, StoryboardScene
from ..prompts import DIALOGUE_SYSTEM, dialogue_prompt
from ..token_tracker import TokenTracker
from ..utils import gemini_retry, parse_json_response

logger = logging.getLogger(__name__)


@gemini_retry()
async def generate_dialogue(
    client: genai.Client,
    state: NovelState,
    chapter_num: int,
    storyboard_scenes: list[StoryboardScene],
    model: str = "gemini-2.5-flash",
    tracker: TokenTracker | None = None,
) -> list[DialogueLine]:
    """Generate narration and dialogue lines for storyboard scenes.

    Returns a list of DialogueLine objects aligned to scene numbers.
    """
    chapter = None
    for ch in state.chapters_written:
        if ch.chapter == chapter_num:
            chapter = ch
            break

    if chapter is None:
        raise ValueError(f"Chapter {chapter_num} not found in state")

    sb_json = json.dumps(
        [s.model_dump() for s in storyboard_scenes],
        ensure_ascii=False,
        indent=2,
    )

    user_msg = dialogue_prompt(chapter_num, chapter.content, sb_json)

    response = await client.aio.models.generate_content(
        model=model,
        contents=user_msg,
        config=genai.types.GenerateContentConfig(
            system_instruction=DIALOGUE_SYSTEM,
            response_mime_type="application/json",
            temperature=0.7,
            max_output_tokens=8192,
        ),
    )

    if tracker and response.usage_metadata:
        tracker.record(
            agent="dialogue",
            chapter=chapter_num,
            input_tokens=response.usage_metadata.prompt_token_count or 0,
            output_tokens=response.usage_metadata.candidates_token_count or 0,
        )

    data = parse_json_response(response.text)
    lines_list = data if isinstance(data, list) else data.get("dialogue", data.get("lines", []))

    lines = [DialogueLine.model_validate(l) for l in lines_list]
    logger.info("Chapter %d dialogue: %d lines", chapter_num, len(lines))
    return lines
