"""Tests for novel_maker.state_manager."""

import pytest
from pathlib import Path

from novel_maker.models import (
    Character,
    ChapterResult,
    Foreshadowing,
    NovelState,
    WorldSetting,
)
from novel_maker.state_manager import StateManager, StateValidationError


@pytest.fixture
def state():
    return NovelState(
        world_setting=WorldSetting(tone="다크", rules=["규칙1"]),
        characters=[
            Character(id=1, name="영희", traits="용감", location="마을", inventory=["검"]),
            Character(id=2, name="철수", traits="겁쟁이", location="성", status="alive"),
            Character(id=3, name="민수", traits="현명", location="숲", status="dead"),
        ],
        foreshadowing=[
            Foreshadowing(id=1, planted_chapter=1, description="복선1"),
            Foreshadowing(id=2, planted_chapter=1, description="복선2"),
        ],
        current_chapter=1,
        total_chapters=3,
    )


@pytest.fixture
def manager(tmp_path):
    return StateManager(output_dir=tmp_path)


class TestCharacterUpdates:
    def test_update_location(self, manager, state):
        updates = [{"name": "영희", "field": "location", "value": "성"}]
        new_state = manager.apply_character_updates(state, updates)
        assert new_state.get_character_by_name("영희").location == "성"
        # Original state unchanged (deepcopy)
        assert state.get_character_by_name("영희").location == "마을"

    def test_update_status(self, manager, state):
        updates = [{"name": "철수", "field": "status", "value": "missing"}]
        new_state = manager.apply_character_updates(state, updates)
        assert new_state.get_character_by_name("철수").status == "missing"

    def test_invalid_status_raises(self, manager, state):
        updates = [{"name": "영희", "field": "status", "value": "sleeping"}]
        with pytest.raises(StateValidationError, match="Invalid status"):
            manager.apply_character_updates(state, updates)

    def test_resurrect_dead_raises(self, manager, state):
        updates = [{"name": "민수", "field": "status", "value": "alive"}]
        with pytest.raises(StateValidationError, match="Cannot resurrect"):
            manager.apply_character_updates(state, updates)

    def test_unknown_character_raises(self, manager, state):
        updates = [{"name": "유령", "field": "location", "value": "어딘가"}]
        with pytest.raises(StateValidationError, match="does not exist"):
            manager.apply_character_updates(state, updates)

    def test_inventory_add(self, manager, state):
        updates = [{"name": "영희", "field": "inventory", "value": {"action": "add", "item": "방패"}}]
        new_state = manager.apply_character_updates(state, updates)
        assert "방패" in new_state.get_character_by_name("영희").inventory
        assert "검" in new_state.get_character_by_name("영희").inventory

    def test_inventory_remove(self, manager, state):
        updates = [{"name": "영희", "field": "inventory", "value": {"action": "remove", "item": "검"}}]
        new_state = manager.apply_character_updates(state, updates)
        assert "검" not in new_state.get_character_by_name("영희").inventory

    def test_inventory_remove_missing_raises(self, manager, state):
        updates = [{"name": "영희", "field": "inventory", "value": {"action": "remove", "item": "없는아이템"}}]
        with pytest.raises(StateValidationError, match="does not have"):
            manager.apply_character_updates(state, updates)

    def test_changelog_recorded(self, manager, state):
        updates = [{"name": "영희", "field": "location", "value": "성"}]
        manager.apply_character_updates(state, updates)
        assert len(manager.changelog) == 1
        assert manager.changelog[0]["type"] == "character_updates"


class TestForeshadowing:
    def test_add_foreshadowing(self, manager, state):
        new_state = manager.add_foreshadowing(state, ["새 복선"])
        assert len(new_state.foreshadowing) == 3
        assert new_state.foreshadowing[2].description == "새 복선"
        assert new_state.foreshadowing[2].id == 3

    def test_resolve_foreshadowing(self, manager, state):
        new_state = manager.resolve_foreshadowing(state, [1])
        resolved = [f for f in new_state.foreshadowing if f.id == 1][0]
        assert resolved.resolved is True
        assert resolved.resolved_chapter == 1

    def test_resolve_already_resolved(self, manager, state):
        state.foreshadowing[0].resolved = True
        # Should log warning but not crash
        new_state = manager.resolve_foreshadowing(state, [1])
        assert new_state is not state  # still returns new copy


class TestFinalizeChapter:
    def test_finalize_advances_chapter(self, manager, state):
        result = ChapterResult(
            chapter=1, content="내용", summary="요약", char_count=10,
        )
        new_state = manager.finalize_chapter(state, result)
        assert new_state.current_chapter == 2
        assert len(new_state.chapters_written) == 1
        assert new_state.current_draft == ""
        assert new_state.revision_count == 0

    def test_finalize_saves_checkpoint(self, manager, state):
        result = ChapterResult(
            chapter=1, content="내용", summary="요약", char_count=10,
        )
        new_state = manager.finalize_chapter(state, result)
        checkpoint_files = list(manager.output_dir.glob("checkpoint_*.json"))
        assert len(checkpoint_files) >= 1


class TestPersistence:
    def test_save_and_load_checkpoint(self, manager, state):
        path = manager.save_checkpoint(state, label="test")
        loaded = manager.load_checkpoint(path)
        assert loaded.current_chapter == state.current_chapter
        assert len(loaded.characters) == len(state.characters)
        assert loaded.world_setting.tone == state.world_setting.tone

    def test_save_state_log(self, manager, state):
        manager.apply_character_updates(
            state, [{"name": "영희", "field": "location", "value": "성"}],
        )
        path = manager.save_state_log()
        assert path.exists()
