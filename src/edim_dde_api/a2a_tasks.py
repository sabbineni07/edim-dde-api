"""In-memory A2A task accept stub (ADR-002 ``running`` status).

When ``async_accept`` is true on generic invoke, the API may return
``status=running`` with a ``task_id`` without blocking on a worker. This
module stores the accepted payload for later poll (GET stub optional).
"""

from __future__ import annotations

import threading
import uuid
from typing import Any

_LOCK = threading.Lock()
_TASKS: dict[str, dict[str, Any]] = {}


def clear_a2a_tasks() -> None:
    """Drop all accepted tasks (tests)."""
    with _LOCK:
        _TASKS.clear()


def accept_task(
    *,
    agent_id: str,
    request_id: str,
    conversation_id: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Record an accepted async task; return task metadata."""
    task_id = str(uuid.uuid4())
    rec = {
        "task_id": task_id,
        "agent_id": agent_id,
        "request_id": request_id,
        "conversation_id": conversation_id,
        "status": "running",
        "payload": dict(payload),
    }
    with _LOCK:
        _TASKS[task_id] = rec
    return rec


def get_task(task_id: str) -> dict[str, Any] | None:
    """Return a stored task or ``None``."""
    tid = (task_id or "").strip()
    if not tid:
        return None
    with _LOCK:
        rec = _TASKS.get(tid)
        return dict(rec) if rec else None
