"""Project storage with pluggable backend (local filesystem or GCS).

Each project is stored under `{prefix}/{project_id}/` with:
  - meta.json: project metadata
  - state.json: full NovelState
  - output/: generated chapter files
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from novel_maker.models import NovelState


# ------------------------------------------------------------------
# Storage Backend ABC
# ------------------------------------------------------------------

class StorageBackend(ABC):
    """Abstract interface for project data storage."""

    @abstractmethod
    def read_file(self, path: str) -> str: ...

    @abstractmethod
    def write_file(self, path: str, content: str) -> None: ...

    @abstractmethod
    def exists(self, path: str) -> bool: ...

    @abstractmethod
    def list_dirs(self, prefix: str) -> list[str]: ...

    @abstractmethod
    def delete_dir(self, path: str) -> None: ...

    @abstractmethod
    def mkdir(self, path: str) -> None: ...

    @abstractmethod
    def write_binary(self, path: str, local_file: Path) -> None:
        """Upload a binary file from local filesystem."""
        ...

    @abstractmethod
    def download_binary(self, path: str, local_dest: Path) -> Path:
        """Download a binary file to local filesystem."""
        ...

    @abstractmethod
    def get_local_path(self, path: str) -> Path:
        """Return a local filesystem path (for tools that need it)."""
        ...


class LocalStorage(StorageBackend):
    """Local filesystem storage (default)."""

    def __init__(self, base_dir: str = "data/projects"):
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)

    def read_file(self, path: str) -> str:
        return (self.base / path).read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> None:
        fp = self.base / path
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")

    def exists(self, path: str) -> bool:
        return (self.base / path).exists()

    def list_dirs(self, prefix: str) -> list[str]:
        d = self.base / prefix if prefix else self.base
        if not d.exists():
            return []
        return sorted([p.name for p in d.iterdir() if p.is_dir()])

    def delete_dir(self, path: str) -> None:
        import shutil
        target = self.base / path
        if target.exists():
            shutil.rmtree(target)

    def mkdir(self, path: str) -> None:
        (self.base / path).mkdir(parents=True, exist_ok=True)

    def write_binary(self, path: str, local_file: Path) -> None:
        """Copy binary file into storage (local = just copy)."""
        import shutil
        dest = self.base / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        if str(local_file) != str(dest):
            shutil.copy2(local_file, dest)

    def download_binary(self, path: str, local_dest: Path) -> Path:
        """For local storage, just return the path."""
        return self.base / path

    def get_local_path(self, path: str) -> Path:
        fp = self.base / path
        fp.parent.mkdir(parents=True, exist_ok=True)
        return fp


class GCSStorage(StorageBackend):
    """Google Cloud Storage backend for production deployments."""

    def __init__(self, bucket_name: str, prefix: str = "projects"):
        from google.cloud import storage as gcs
        self.client = gcs.Client()
        self.bucket = self.client.bucket(bucket_name)
        self.prefix = prefix
        self._local_cache = Path("/tmp/novelmaker_cache")
        self._local_cache.mkdir(parents=True, exist_ok=True)

    def _blob_path(self, path: str) -> str:
        return f"{self.prefix}/{path}"

    def read_file(self, path: str) -> str:
        blob = self.bucket.blob(self._blob_path(path))
        return blob.download_as_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> None:
        blob = self.bucket.blob(self._blob_path(path))
        blob.upload_from_string(content, content_type="application/json")

    def exists(self, path: str) -> bool:
        blob = self.bucket.blob(self._blob_path(path))
        return blob.exists()

    def list_dirs(self, prefix: str) -> list[str]:
        full_prefix = f"{self.prefix}/{prefix}/" if prefix else f"{self.prefix}/"
        blobs = self.client.list_blobs(self.bucket, prefix=full_prefix, delimiter="/")
        # Trigger the iteration to populate prefixes
        list(blobs)
        dirs = []
        for p in blobs.prefixes:
            name = p.rstrip("/").split("/")[-1]
            dirs.append(name)
        return sorted(dirs)

    def delete_dir(self, path: str) -> None:
        full_prefix = self._blob_path(path) + "/"
        blobs = list(self.client.list_blobs(self.bucket, prefix=full_prefix))
        if blobs:
            self.bucket.delete_blobs(blobs)

    def mkdir(self, path: str) -> None:
        pass  # GCS doesn't need explicit directory creation

    def write_binary(self, path: str, local_file: Path) -> None:
        """Upload a binary file (mp3, mp4, epub, pdf, etc.) to GCS."""
        blob = self.bucket.blob(self._blob_path(path))
        blob.upload_from_filename(str(local_file))

    def download_binary(self, path: str, local_dest: Path) -> Path:
        """Download a binary file from GCS to local path."""
        local_dest.parent.mkdir(parents=True, exist_ok=True)
        blob = self.bucket.blob(self._blob_path(path))
        if blob.exists():
            blob.download_to_filename(str(local_dest))
        return local_dest

    def get_local_path(self, path: str) -> Path:
        """Return a local filesystem path, downloading from GCS if needed."""
        local = self._local_cache / path
        local.parent.mkdir(parents=True, exist_ok=True)
        if self.exists(path) and not local.exists():
            blob = self.bucket.blob(self._blob_path(path))
            blob.download_to_filename(str(local))
        return local


# ------------------------------------------------------------------
# Backend selection
# ------------------------------------------------------------------

def _get_backend() -> StorageBackend:
    backend_type = os.getenv("STORAGE_BACKEND", "local")
    if backend_type == "gcs":
        bucket = os.getenv("GCS_BUCKET_NAME")
        if not bucket:
            raise ValueError("GCS_BUCKET_NAME env var required when STORAGE_BACKEND=gcs")
        return GCSStorage(bucket_name=bucket)
    return LocalStorage()


_backend = _get_backend()


# ------------------------------------------------------------------
# Per-project locks
# ------------------------------------------------------------------

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


# ------------------------------------------------------------------
# Helper paths (relative to backend root)
# ------------------------------------------------------------------

def _meta_rel(project_id: str) -> str:
    return f"{project_id}/meta.json"


def _state_rel(project_id: str) -> str:
    return f"{project_id}/state.json"


def _output_rel(project_id: str) -> str:
    return f"{project_id}/output"


# ------------------------------------------------------------------
# Project CRUD
# ------------------------------------------------------------------

def create_project(title: str, logline: str, total_chapters: int = 3) -> dict:
    """Create a new project with initial state."""
    project_id = uuid.uuid4().hex[:12]
    _backend.mkdir(project_id)
    _backend.mkdir(_output_rel(project_id))

    now = time.time()
    meta = ProjectMeta(
        project_id=project_id,
        title=title,
        logline=logline,
        created_at=now,
        updated_at=now,
    )
    _backend.write_file(
        _meta_rel(project_id),
        json.dumps(meta.to_dict(), ensure_ascii=False, indent=2),
    )

    state = NovelState(total_chapters=total_chapters)
    save_state(project_id, state)

    return {**meta.to_dict(), "state": state.model_dump()}


def list_projects() -> list[dict]:
    """List all projects with metadata."""
    projects = []
    for dirname in _backend.list_dirs(""):
        meta_path = f"{dirname}/meta.json"
        if _backend.exists(meta_path):
            meta = json.loads(_backend.read_file(meta_path))
            state_path = f"{dirname}/state.json"
            if _backend.exists(state_path):
                state_data = json.loads(_backend.read_file(state_path))
                meta["chapters_written"] = len(state_data.get("chapters_written", []))
                meta["total_chapters"] = state_data.get("total_chapters", 0)
                meta["character_count"] = len(state_data.get("characters", []))
                meta["phase"] = state_data.get("phase", "planning")
            projects.append(meta)
    return projects


def get_project(project_id: str) -> dict | None:
    """Get project metadata and state."""
    if not _backend.exists(_meta_rel(project_id)):
        return None
    meta = json.loads(_backend.read_file(_meta_rel(project_id)))
    state = load_state(project_id)
    return {**meta, "state": state.model_dump() if state else None}


def delete_project(project_id: str) -> bool:
    """Delete a project."""
    if not _backend.exists(_meta_rel(project_id)):
        return False
    _backend.delete_dir(project_id)
    return True


def update_meta(project_id: str, **kwargs) -> dict | None:
    """Update project metadata fields."""
    if not _backend.exists(_meta_rel(project_id)):
        return None
    meta = json.loads(_backend.read_file(_meta_rel(project_id)))
    meta.update(kwargs)
    meta["updated_at"] = time.time()
    _backend.write_file(
        _meta_rel(project_id),
        json.dumps(meta, ensure_ascii=False, indent=2),
    )
    return meta


# ------------------------------------------------------------------
# State persistence
# ------------------------------------------------------------------

def save_state(project_id: str, state: NovelState) -> None:
    """Save NovelState."""
    _backend.write_file(
        _state_rel(project_id),
        state.model_dump_json(indent=2),
    )
    update_meta(project_id)  # touch updated_at


def load_state(project_id: str) -> NovelState | None:
    """Load NovelState."""
    if not _backend.exists(_state_rel(project_id)):
        return None
    data = json.loads(_backend.read_file(_state_rel(project_id)))
    return NovelState.model_validate(data)


def get_output_dir(project_id: str) -> Path:
    """Return a local filesystem path for the output directory."""
    rel = _output_rel(project_id)
    _backend.mkdir(rel)
    return _backend.get_local_path(rel).parent / "output" if not isinstance(_backend, LocalStorage) else _backend.get_local_path(rel)
