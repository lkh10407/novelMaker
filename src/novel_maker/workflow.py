"""Workflow — orchestrates the multi-agent novel pipeline.

Implements the full write → check → refine loop with dynamic
re-planning, state validation, and checkpoint persistence.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from pathlib import Path

from google import genai
from tenacity import retry, stop_after_attempt, wait_exponential

from .agents.checker import check_chapter
from .agents.planner import plan_novel
from .agents.refiner import refine_chapter
from .agents.writer import write_chapter
from .models import (
    ChapterOutline,
    ChapterResult,
    NovelState,
)
from .prompts import (
    REPLANNER_SYSTEM,
    STATE_UPDATER_SYSTEM,
    replanner_prompt,
    state_updater_prompt,
)
from .state_manager import StateManager
from .token_tracker import TokenTracker
from .utils import parse_json_response

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Helper: call Gemini for state update extraction
# ------------------------------------------------------------------

@retry(
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def _extract_state_changes(
    client: genai.Client,
    chapter_content: str,
    state: NovelState,
    model: str,
    tracker: TokenTracker | None,
) -> dict:
    """Ask Gemini to extract state changes from a completed chapter."""
    chars_json = json.dumps(
        [ch.model_dump() for ch in state.characters],
        ensure_ascii=False, indent=2,
    )
    user_msg = state_updater_prompt(chapter_content, chars_json)

    response = await client.aio.models.generate_content(
        model=model,
        contents=user_msg,
        config=genai.types.GenerateContentConfig(
            system_instruction=STATE_UPDATER_SYSTEM,
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )

    if tracker and response.usage_metadata:
        tracker.record(
            agent="state_updater",
            chapter=state.current_chapter,
            input_tokens=response.usage_metadata.prompt_token_count or 0,
            output_tokens=response.usage_metadata.candidates_token_count or 0,
        )

    return parse_json_response(response.text)


@retry(
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def _replan(
    client: genai.Client,
    state: NovelState,
    model: str,
    tracker: TokenTracker | None,
) -> list[ChapterOutline]:
    """Re-plan remaining chapters based on story progress."""
    summaries = " → ".join(ch.summary for ch in state.chapters_written)
    remaining = [
        ol for ol in state.plot_outline
        if ol.chapter >= state.current_chapter
    ]
    remaining_json = json.dumps(
        [ol.model_dump() for ol in remaining],
        ensure_ascii=False, indent=2,
    )
    fs_json = json.dumps(
        [f.model_dump() for f in state.get_open_foreshadowing()],
        ensure_ascii=False, indent=2,
    )

    user_msg = replanner_prompt(summaries, remaining_json, fs_json)

    response = await client.aio.models.generate_content(
        model=model,
        contents=user_msg,
        config=genai.types.GenerateContentConfig(
            system_instruction=REPLANNER_SYSTEM,
            response_mime_type="application/json",
            temperature=0.5,
        ),
    )

    if tracker and response.usage_metadata:
        tracker.record(
            agent="replanner",
            chapter=state.current_chapter,
            input_tokens=response.usage_metadata.prompt_token_count or 0,
            output_tokens=response.usage_metadata.candidates_token_count or 0,
        )

    data = parse_json_response(response.text)

    # Handle both direct list and wrapped object
    outline_list = data if isinstance(data, list) else data.get("plot_outline", data.get("chapters", []))

    return [ChapterOutline.model_validate(ol) for ol in outline_list]


# ------------------------------------------------------------------
# Main pipeline runner
# ------------------------------------------------------------------

class NovelPipeline:
    """Orchestrates the full novel generation pipeline."""

    def __init__(
        self,
        client: genai.Client,
        model: str = "gemini-2.5-flash",
        output_dir: Path | None = None,
        replan_interval: int = 3,
    ):
        self.client = client
        self.model = model
        self.output_dir = output_dir or Path("output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.replan_interval = replan_interval
        self.tracker = TokenTracker(model_name=model)
        self.state_manager = StateManager(output_dir=self.output_dir)

        # Callbacks for UI updates
        self.on_phase_change: Callable | None = None
        self.on_chapter_complete: Callable | None = None

        # HITL: approval queue for interactive mode
        self.approval_queue: asyncio.Queue | None = None

        # RAG: long-term memory store
        self.memory_store = None  # MemoryStore | None

    def _notify(self, phase: str, **kwargs):
        if self.on_phase_change:
            self.on_phase_change(phase, **kwargs)

    def _state_has_plan(self, state: NovelState) -> bool:
        """Check if a state already has a usable plan (characters + outline)."""
        return bool(state.characters and state.plot_outline)

    async def run(
        self,
        logline: str,
        total_chapters: int = 3,
        language: str = "ko",
        resume_from: Path | None = None,
        existing_state: NovelState | None = None,
    ) -> NovelState:
        """Run the full novel generation pipeline.

        Args:
            logline: One-line story idea.
            total_chapters: Number of chapters to generate.
            language: Target language.
            resume_from: Path to a checkpoint file to resume from.
            existing_state: Pre-configured state (e.g. from server API edits).
                If provided with characters and outline, planning is skipped.

        Returns:
            The final NovelState with all chapters written.
        """

        # ---- Phase 1: Planning (or resume / use existing) ----
        if resume_from and resume_from.exists():
            logger.info("Resuming from checkpoint: %s", resume_from)
            state = self.state_manager.load_checkpoint(resume_from)
            self._notify("resumed", chapter=state.current_chapter)
        elif existing_state and self._state_has_plan(existing_state):
            logger.info("Using existing state (characters=%d, outline=%d chapters)",
                        len(existing_state.characters), len(existing_state.plot_outline))
            state = existing_state
            state.total_chapters = total_chapters
            self._notify("resumed", chapter=state.current_chapter)
            self.state_manager.save_checkpoint(state, label="pre_edited")
        else:
            self._notify("planning")
            state = await plan_novel(
                client=self.client,
                logline=logline,
                total_chapters=total_chapters,
                language=language,
                model=self.model,
                tracker=self.tracker,
            )
            self.state_manager.save_checkpoint(state, label="planned")

        # ---- Phase 2: Chapter loop ----
        while state.current_chapter <= state.total_chapters:
            ch_num = state.current_chapter
            logger.info("=== Chapter %d/%d ===", ch_num, state.total_chapters)

            state, chapter_result = await self._process_single_chapter(state)

            if self.on_chapter_complete:
                self.on_chapter_complete(ch_num, chapter_result)

            # -- HITL: await user approval if interactive mode --
            if self.approval_queue is not None and state.current_chapter <= state.total_chapters:
                state.phase = "awaiting_approval"
                self._notify(
                    "awaiting_approval",
                    chapter=ch_num,
                    content=chapter_result.content,
                    summary=chapter_result.summary,
                )
                logger.info("Chapter %d: awaiting user approval", ch_num)
                approval = await self.approval_queue.get()

                # Apply user edits if provided
                if approval.get("edited_content"):
                    edited = approval["edited_content"]
                    chapter_result.content = edited
                    chapter_result.char_count = len(edited)
                    # Update stored chapter and file
                    state.chapters_written[-1] = chapter_result
                    ch_path = self.output_dir / f"chapter_{ch_num:02d}.md"
                    ch_path.write_text(
                        f"# {ch_num}장\n\n{edited}",
                        encoding="utf-8",
                    )
                    logger.info("Chapter %d: user edited content applied", ch_num)

                # Store user guidance for next chapter
                guidance = approval.get("guidance", "")
                state.user_guidance = guidance
                if guidance:
                    logger.info("Chapter %d: user guidance for next chapter: %s", ch_num, guidance[:80])

            # -- Re-plan check --
            if (
                ch_num % self.replan_interval == 0
                and state.current_chapter <= state.total_chapters
            ):
                state.phase = "replanning"
                self._notify("replanning", chapter=ch_num)
                logger.info("Re-planning after chapter %d", ch_num)

                try:
                    new_outlines = await _replan(
                        client=self.client,
                        state=state,
                        model=self.model,
                        tracker=self.tracker,
                    )
                    # Replace remaining outlines
                    kept = [
                        ol for ol in state.plot_outline
                        if ol.chapter < state.current_chapter
                    ]
                    state.plot_outline = kept + new_outlines
                    logger.info("Re-plan complete: %d chapters remaining", len(new_outlines))
                except Exception as e:
                    logger.warning("Re-planning failed (continuing with original): %s", e)

        # ---- Phase 3: Output ----
        state.phase = "done"
        self._notify("done")

        # Assemble final manuscript
        self._save_final_manuscript(state)
        self.state_manager.save_state_log()
        self.tracker.save(self.output_dir)

        return state

    async def _process_single_chapter(
        self,
        state: NovelState,
        skip_finalize: bool = False,
    ) -> tuple[NovelState, ChapterResult]:
        """Write, check, refine, and finalize a single chapter.

        Returns the updated state and the ChapterResult.
        """
        ch_num = state.current_chapter
        outline = state.get_current_outline()

        # -- Write --
        state.phase = "writing"
        self._notify("writing", chapter=ch_num)

        draft = await write_chapter(
            client=self.client,
            state=state,
            model=self.model,
            tracker=self.tracker,
            memory_store=self.memory_store,
        )
        state.current_draft = draft
        state.revision_count = 0
        state.revision_history = []

        # -- Check/Refine loop --
        while True:
            state.phase = "checking"
            self._notify("checking", chapter=ch_num, revision=state.revision_count)

            check_result = await check_chapter(
                client=self.client,
                state=state,
                draft=state.current_draft,
                model=self.model,
                tracker=self.tracker,
            )
            state.checker_result = check_result
            state.revision_history.append(check_result)

            if check_result.passed:
                logger.info("Chapter %d PASSED", ch_num)
                break

            if state.revision_count >= state.max_revisions:
                logger.warning(
                    "Chapter %d: max revisions (%d) reached — forcing PASS",
                    ch_num, state.max_revisions,
                )
                break

            state.phase = "refining"
            self._notify(
                "refining",
                chapter=ch_num,
                revision=state.revision_count + 1,
                errors=[e.code for e in check_result.errors],
            )

            refined = await refine_chapter(
                client=self.client,
                state=state,
                draft=state.current_draft,
                check_result=check_result,
                model=self.model,
                tracker=self.tracker,
            )
            state.current_draft = refined
            state.revision_count += 1

        # -- Extract state changes --
        state.phase = "updating"
        self._notify("updating_state", chapter=ch_num)

        changes = await _extract_state_changes(
            client=self.client,
            chapter_content=state.current_draft,
            state=state,
            model=self.model,
            tracker=self.tracker,
        )

        chapter_result = ChapterResult(
            chapter=ch_num,
            content=state.current_draft,
            summary=changes.get("summary", ""),
            ending_hook=changes.get("ending_hook", ""),
            state_changes=changes.get("state_changes", []),
            char_count=len(state.current_draft),
        )

        # Apply character updates
        char_updates = changes.get("character_updates", [])
        if char_updates:
            try:
                state = self.state_manager.apply_character_updates(
                    state, char_updates,
                )
            except Exception as e:
                logger.warning(
                    "State update validation failed for chapter %d: %s. "
                    "Skipping character updates — state preserved.",
                    ch_num, e,
                )

        # Apply foreshadowing
        new_fs = changes.get("new_foreshadowing", [])
        if new_fs:
            state = self.state_manager.add_foreshadowing(state, new_fs)

        resolved_fs = changes.get("resolved_foreshadowing_ids", [])
        if resolved_fs:
            state = self.state_manager.resolve_foreshadowing(state, resolved_fs)

        if not skip_finalize:
            state = self.state_manager.finalize_chapter(state, chapter_result)

        # Save chapter content to file
        ch_path = self.output_dir / f"chapter_{ch_num:02d}.md"
        ch_path.write_text(
            f"# {ch_num}장\n\n{chapter_result.content}",
            encoding="utf-8",
        )

        # Store chapter in RAG memory
        if self.memory_store is not None:
            try:
                involved = (
                    [outline.pov_character] + list(outline.involved_characters)
                    if outline else []
                )
                await self.memory_store.store_chapter(
                    chapter_num=ch_num,
                    content=chapter_result.content,
                    characters=involved,
                    events=chapter_result.state_changes,
                )
            except Exception as e:
                logger.warning("Memory store failed for chapter %d: %s", ch_num, e)

        return state, chapter_result

    async def regenerate_chapter(
        self,
        state: NovelState,
        chapter_num: int,
        guidance: str = "",
    ) -> NovelState:
        """Regenerate a specific chapter in-place.

        The chapter must already exist in chapters_written.
        Other chapters remain unchanged.
        """
        # Temporarily set current_chapter to the target
        original_current = state.current_chapter
        state.current_chapter = chapter_num
        state.user_guidance = guidance
        state.revision_count = 0
        state.revision_history = []

        state, new_result = await self._process_single_chapter(state, skip_finalize=True)

        # Replace the existing chapter in chapters_written
        for i, ch in enumerate(state.chapters_written):
            if ch.chapter == chapter_num:
                state.chapters_written[i] = new_result
                break

        # Restore current chapter pointer
        state.current_chapter = original_current
        state.current_draft = ""
        state.user_guidance = ""

        return state

    def _save_final_manuscript(self, state: NovelState) -> Path:
        """Combine all chapters into a single markdown file."""
        parts: list[str] = []
        parts.append(f"# {state.world_setting.tone} 소설\n")
        parts.append(f"> 총 {state.total_chapters}장\n\n---\n")

        for ch_result in state.chapters_written:
            parts.append(f"\n## {ch_result.chapter}장\n")
            parts.append(ch_result.content)
            parts.append("\n\n---\n")

        path = self.output_dir / "novel.md"
        path.write_text("\n".join(parts), encoding="utf-8")
        logger.info("Final manuscript saved: %s", path)
        return path
