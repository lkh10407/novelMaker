"""JSON file-based project storage.

Each project is stored as a directory under `data/projects/{project_id}/`
with a `state.json` file containing the full NovelState.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path

from novel_maker.models import NovelState


DATA_DIR = Path("data/projects")

# Per-project locks to prevent concurrent read-modify-write races.
_locks: dict[str, asyncio.Lock] = {}


def get_lock(project_id: str) -> asyncio.Lock:
    """Get or create an asyncio.Lock for a given project."""
    if project_id not in _locks:
        _locks[project_id] = asyncio.Lock()
    return _locks[project_id]


class ProjectMeta:
    """Lightweight project metadata."""

    def __init__(self, project_id: str, title: str, logline: str, created_at: float, updated_at: float):
        self.project_id = project_id
        self.title = title
        self.logline = logline
        self.created_at = created_at
        self.updated_at = updated_at

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "title": self.title,
            "logline": self.logline,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProjectMeta":
        return cls(**d)


def _project_dir(project_id: str) -> Path:
    return DATA_DIR / project_id


def _meta_path(project_id: str) -> Path:
    return _project_dir(project_id) / "meta.json"


def _state_path(project_id: str) -> Path:
    return _project_dir(project_id) / "state.json"


def _output_dir(project_id: str) -> Path:
    return _project_dir(project_id) / "output"


# ------------------------------------------------------------------
# Project CRUD
# ------------------------------------------------------------------

def create_project(title: str, logline: str, total_chapters: int = 3) -> dict:
    """Create a new project directory with initial state."""
    project_id = uuid.uuid4().hex[:12]
    d = _project_dir(project_id)
    d.mkdir(parents=True, exist_ok=True)
    _output_dir(project_id).mkdir(exist_ok=True)

    now = time.time()
    meta = ProjectMeta(
        project_id=project_id,
        title=title,
        logline=logline,
        created_at=now,
        updated_at=now,
    )
    _meta_path(project_id).write_text(
        json.dumps(meta.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    state = NovelState(total_chapters=total_chapters)
    save_state(project_id, state)

    return {**meta.to_dict(), "state": state.model_dump()}


def list_projects() -> list[dict]:
    """List all projects with metadata."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    projects = []
    for d in sorted(DATA_DIR.iterdir()):
        mp = d / "meta.json"
        if mp.exists():
            meta = json.loads(mp.read_text(encoding="utf-8"))
            # Add progress info
            sp = d / "state.json"
            if sp.exists():
                state_data = json.loads(sp.read_text(encoding="utf-8"))
                meta["chapters_written"] = len(state_data.get("chapters_written", []))
                meta["total_chapters"] = state_data.get("total_chapters", 0)
                meta["character_count"] = len(state_data.get("characters", []))
                meta["phase"] = state_data.get("phase", "planning")
            projects.append(meta)
    return projects


def get_project(project_id: str) -> dict | None:
    """Get project metadata and state."""
    mp = _meta_path(project_id)
    if not mp.exists():
        return None
    meta = json.loads(mp.read_text(encoding="utf-8"))
    state = load_state(project_id)
    return {**meta, "state": state.model_dump() if state else None}


def delete_project(project_id: str) -> bool:
    """Delete a project directory."""
    import shutil
    d = _project_dir(project_id)
    if d.exists():
        shutil.rmtree(d)
        return True
    return False


def update_meta(project_id: str, **kwargs) -> dict | None:
    """Update project metadata fields."""
    mp = _meta_path(project_id)
    if not mp.exists():
        return None
    meta = json.loads(mp.read_text(encoding="utf-8"))
    meta.update(kwargs)
    meta["updated_at"] = time.time()
    mp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


# ------------------------------------------------------------------
# State persistence
# ------------------------------------------------------------------

def save_state(project_id: str, state: NovelState) -> None:
    """Save NovelState to disk."""
    _state_path(project_id).write_text(
        state.model_dump_json(indent=2),
        encoding="utf-8",
    )
    update_meta(project_id)  # touch updated_at


def load_state(project_id: str) -> NovelState | None:
    """Load NovelState from disk."""
    sp = _state_path(project_id)
    if not sp.exists():
        return None
    data = json.loads(sp.read_text(encoding="utf-8"))
    return NovelState.model_validate(data)


def get_output_dir(project_id: str) -> Path:
    """Return the output directory for a project."""
    d = _output_dir(project_id)
    d.mkdir(parents=True, exist_ok=True)
    return d
