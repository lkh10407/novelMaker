"""Real-time collaboration WebSocket endpoint."""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..collab_manager import collab_manager
from ..storage import load_state, save_state, get_lock

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws/{project_id}")
async def collab_websocket(websocket: WebSocket, project_id: str):
    """WebSocket endpoint for real-time collaboration.

    Message types from client:
    - {"action": "lock", "chapter": int}
    - {"action": "unlock", "chapter": int}
    - {"action": "save", "chapter": int, "content": str, "summary": str}
    """
    user_id = str(uuid.uuid4())[:8]
    room = collab_manager.get_or_create_room(project_id)

    await room.connect(user_id, websocket)
    logger.info("User %s connected to project %s", user_id, project_id)

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            chapter = data.get("chapter")

            if action == "lock" and chapter is not None:
                success = room.acquire_lock(chapter, user_id)
                if success:
                    await websocket.send_json({
                        "type": "lock_acquired",
                        "chapter": chapter,
                    })
                    await room.broadcast({
                        "type": "chapter_locked",
                        "chapter": chapter,
                        "user_id": user_id,
                    }, exclude=user_id)
                else:
                    existing = room.locks.get(chapter)
                    await websocket.send_json({
                        "type": "lock_denied",
                        "chapter": chapter,
                        "locked_by": existing.user_id if existing else "unknown",
                    })

            elif action == "unlock" and chapter is not None:
                room.release_lock(chapter, user_id)
                await room.broadcast({
                    "type": "chapter_unlocked",
                    "chapter": chapter,
                })

            elif action == "save" and chapter is not None:
                content = data.get("content", "")
                summary = data.get("summary", "")

                async with get_lock(project_id):
                    state = load_state(project_id)
                    if state:
                        for ch in state.chapters_written:
                            if ch.chapter == chapter:
                                ch.content = content
                                ch.char_count = len(content)
                                if summary:
                                    ch.summary = summary
                                break
                        save_state(project_id, state)

                # Release lock after save
                room.release_lock(chapter, user_id)

                # Broadcast update to all clients
                await room.broadcast({
                    "type": "chapter_updated",
                    "chapter": chapter,
                    "user_id": user_id,
                    "char_count": len(content),
                    "summary": summary,
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("WebSocket error for user %s: %s", user_id, e)
    finally:
        # Broadcast user left and release locks
        room.disconnect(user_id)
        await room.broadcast({
            "type": "user_left",
            "user_id": user_id,
            "users": list(room.connections.keys()),
        })
        collab_manager.cleanup_room(project_id)
        logger.info("User %s disconnected from project %s", user_id, project_id)
