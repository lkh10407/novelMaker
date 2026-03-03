"""Collaboration manager — lock-based chapter editing with broadcast.

MVP approach: only one user can edit a chapter at a time.
Changes are broadcast to all connected clients via WebSocket.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field

from fastapi import WebSocket

logger = logging.getLogger(__name__)

LOCK_TIMEOUT_SECONDS = 300  # 5 minutes


@dataclass
class ChapterLock:
    """Represents an editing lock on a chapter."""

    chapter_num: int
    user_id: str
    acquired_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        return (time.time() - self.acquired_at) > LOCK_TIMEOUT_SECONDS


class CollabRoom:
    """Manages a single project's collaboration state."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.connections: dict[str, WebSocket] = {}  # user_id -> ws
        self.locks: dict[int, ChapterLock] = {}  # chapter_num -> lock

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.connections[user_id] = ws
        # Send current lock state
        await ws.send_json({
            "type": "init",
            "locks": {
                str(ch): {"user_id": lock.user_id}
                for ch, lock in self.locks.items()
                if not lock.is_expired()
            },
            "users": list(self.connections.keys()),
        })
        # Broadcast user joined
        await self.broadcast({
            "type": "user_joined",
            "user_id": user_id,
            "users": list(self.connections.keys()),
        }, exclude=user_id)

    def disconnect(self, user_id: str):
        self.connections.pop(user_id, None)
        # Release any locks held by this user
        expired = [ch for ch, lock in self.locks.items() if lock.user_id == user_id]
        for ch in expired:
            del self.locks[ch]

    async def broadcast(self, message: dict, exclude: str | None = None):
        dead: list[str] = []
        for uid, ws in self.connections.items():
            if uid == exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(uid)
        for uid in dead:
            self.disconnect(uid)

    def acquire_lock(self, chapter_num: int, user_id: str) -> bool:
        """Try to acquire a lock on a chapter."""
        existing = self.locks.get(chapter_num)
        if existing and not existing.is_expired() and existing.user_id != user_id:
            return False
        self.locks[chapter_num] = ChapterLock(chapter_num=chapter_num, user_id=user_id)
        return True

    def release_lock(self, chapter_num: int, user_id: str) -> bool:
        """Release a lock on a chapter."""
        existing = self.locks.get(chapter_num)
        if existing and (existing.user_id == user_id or existing.is_expired()):
            del self.locks[chapter_num]
            return True
        return False

    def is_empty(self) -> bool:
        return len(self.connections) == 0


class CollabManager:
    """Global collaboration manager for all projects."""

    def __init__(self):
        self.rooms: dict[str, CollabRoom] = {}

    def get_or_create_room(self, project_id: str) -> CollabRoom:
        if project_id not in self.rooms:
            self.rooms[project_id] = CollabRoom(project_id)
        return self.rooms[project_id]

    def cleanup_room(self, project_id: str):
        room = self.rooms.get(project_id)
        if room and room.is_empty():
            del self.rooms[project_id]


# Global singleton
collab_manager = CollabManager()
