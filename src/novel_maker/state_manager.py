"""State Manager — validates and applies state changes after each chapter.

Ensures that LLM-generated state updates conform to model constraints
and logs all changes for auditability.
"""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from pathlib import Path

from pydantic import ValidationError

from .models import Character, ChapterResult, Foreshadowing, NovelState

logger = logging.getLogger(__name__)


class StateValidationError(Exception):
    """Raised when a proposed state change is invalid."""


class StateManager:
    """Manages novel state lifecycle: initialization, update, persistence."""

    def __init__(self, output_dir: Path | None = None):
        self.output_dir = output_dir or Path("output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.changelog: list[dict] = []

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def save_checkpoint(self, state: NovelState, label: str = "") -> Path:
        """Save current state to a JSON checkpoint file."""
        suffix = f"_{label}" if label else ""
        path = self.output_dir / f"checkpoint_ch{state.current_chapter}{suffix}.json"
        path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        logger.info("Checkpoint saved: %s", path)
        return path

    def load_checkpoint(self, path: Path) -> NovelState:
        """Load state from a checkpoint file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return NovelState.model_validate(data)

    def save_state_log(self) -> Path:
        """Write the full changelog to disk."""
        path = self.output_dir / "state_log.json"
        path.write_text(json.dumps(self.changelog, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    # ------------------------------------------------------------------
    # Character state updates
    # ------------------------------------------------------------------

    def apply_character_updates(
        self,
        state: NovelState,
        updates: list[dict],
    ) -> NovelState:
        """Apply a list of character updates with validation.

        Each update dict should have:
            - name: str (character name)
            - field: str (field to update)
            - value: any (new value)

        Raises StateValidationError for invalid updates.
        """
        new_state = deepcopy(state)

        for upd in updates:
            char_name = upd.get("name", "")
            field = upd.get("field", "")
            value = upd.get("value")

            char = new_state.get_character_by_name(char_name)
            if char is None:
                raise StateValidationError(
                    f"Character '{char_name}' does not exist in state"
                )

            # Validate specific constraints
            if field == "status":
                if value not in ("alive", "dead", "missing"):
                    raise StateValidationError(
                        f"Invalid status '{value}' for {char_name}. "
                        f"Must be alive/dead/missing."
                    )
                # Cannot resurrect dead characters
                if char.status == "dead" and value == "alive":
                    raise StateValidationError(
                        f"Cannot resurrect dead character '{char_name}'"
                    )

            if field == "inventory" and isinstance(value, dict):
                action = value.get("action")
                item = value.get("item", "")
                if action == "add":
                    char.inventory.append(item)
                elif action == "remove":
                    if item not in char.inventory:
                        raise StateValidationError(
                            f"'{char_name}' does not have '{item}' in inventory"
                        )
                    char.inventory.remove(item)
                continue

            if hasattr(char, field):
                setattr(char, field, value)
            else:
                logger.warning("Unknown field '%s' for character update", field)

            # Re-validate the character model
            try:
                Character.model_validate(char.model_dump())
            except ValidationError as e:
                raise StateValidationError(
                    f"Validation failed for {char_name}: {e}"
                ) from e

        # Log changes
        self.changelog.append({
            "chapter": state.current_chapter,
            "type": "character_updates",
            "updates": updates,
        })

        return new_state

    # ------------------------------------------------------------------
    # Foreshadowing management
    # ------------------------------------------------------------------

    def add_foreshadowing(
        self,
        state: NovelState,
        descriptions: list[str],
    ) -> NovelState:
        """Add new foreshadowing entries planted in the current chapter."""
        new_state = deepcopy(state)
        max_id = max((f.id for f in new_state.foreshadowing), default=0)

        for desc in descriptions:
            max_id += 1
            new_state.foreshadowing.append(
                Foreshadowing(
                    id=max_id,
                    planted_chapter=state.current_chapter,
                    description=desc,
                )
            )

        self.changelog.append({
            "chapter": state.current_chapter,
            "type": "foreshadowing_added",
            "descriptions": descriptions,
        })

        return new_state

    def resolve_foreshadowing(
        self,
        state: NovelState,
        foreshadowing_ids: list[int],
    ) -> NovelState:
        """Mark foreshadowing entries as resolved."""
        new_state = deepcopy(state)

        for fid in foreshadowing_ids:
            for f in new_state.foreshadowing:
                if f.id == fid and not f.resolved:
                    f.resolved = True
                    f.resolved_chapter = state.current_chapter
                    break
            else:
                logger.warning("Foreshadowing id=%d not found or already resolved", fid)

        self.changelog.append({
            "chapter": state.current_chapter,
            "type": "foreshadowing_resolved",
            "ids": foreshadowing_ids,
        })

        return new_state

    # ------------------------------------------------------------------
    # Chapter finalization
    # ------------------------------------------------------------------

    def finalize_chapter(
        self,
        state: NovelState,
        chapter_result: ChapterResult,
    ) -> NovelState:
        """Add a completed chapter to state and advance to the next."""
        new_state = deepcopy(state)
        new_state.chapters_written.append(chapter_result)
        new_state.current_draft = ""
        new_state.revision_count = 0
        new_state.revision_history = []
        new_state.checker_result = None
        new_state.current_chapter += 1
        new_state.phase = "updating"

        self.changelog.append({
            "chapter": chapter_result.chapter,
            "type": "chapter_finalized",
            "summary": chapter_result.summary,
            "state_changes": chapter_result.state_changes,
            "char_count": chapter_result.char_count,
        })

        # Auto-save checkpoint
        self.save_checkpoint(new_state, label="finalized")

        return new_state
