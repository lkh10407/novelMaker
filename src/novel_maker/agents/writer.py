"""Writer Agent — drafts a single chapter of the novel.

Uses the optimised context from ContextBuilder to produce
a chapter that respects character states and narrative continuity.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from google import genai

from ..context_builder import WriterContext, build_writer_context
from ..models import NovelState
from ..prompts import WRITER_SYSTEM, writer_prompt
from ..token_tracker import TokenTracker
from ..utils import gemini_retry

if TYPE_CHECKING:
    from ..memory import MemoryStore

logger = logging.getLogger(__name__)


@gemini_retry()
async def write_chapter(
    client: genai.Client,
    state: NovelState,
    model: str = "gemini-2.5-flash",
    tracker: TokenTracker | None = None,
    memory_store: MemoryStore | None = None,
) -> str:
    """Draft the current chapter based on state and context.

    Returns the raw chapter text.
    """
    chapter_num = state.current_chapter
    logger.info("Writing chapter %d", chapter_num)

    # Build optimised context (now async to support RAG queries)
    ctx: WriterContext = await build_writer_context(state, memory_store=memory_store)
    context_text = ctx.to_prompt_text()

    # Include user guidance if provided
    guidance_text = ""
    if state.user_guidance:
        guidance_text = f"\n\n## 사용자 지시사항\n{state.user_guidance}"

    user_msg = writer_prompt(context_text + guidance_text)

    response = await client.aio.models.generate_content(
        model=model,
        contents=user_msg,
        config=genai.types.GenerateContentConfig(
            system_instruction=WRITER_SYSTEM,
            temperature=0.9,
            max_output_tokens=8192,
        ),
    )

    # Track tokens
    if tracker and response.usage_metadata:
        tracker.record(
            agent="writer",
            chapter=chapter_num,
            input_tokens=response.usage_metadata.prompt_token_count or 0,
            output_tokens=response.usage_metadata.candidates_token_count or 0,
        )

    draft = response.text.strip()
    logger.info("Chapter %d draft: %d chars", chapter_num, len(draft))
    return draft
