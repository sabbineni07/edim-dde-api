"""In-process A2A task worker (ADR-002 durable async follow-on).

Accept returns ``running`` + ``task_id``; this module runs ``create_agent``
on a thread pool and updates the task store to ``completed`` /
``input_needed`` / ``error``. Not a queue-scaled ACA worker — same contract,
local execution.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from edim_dde_ai import create_agent
from edim_dde_ai.a2a.tasks import (
    STATUS_COMPLETED,
    STATUS_ERROR,
    STATUS_INPUT_NEEDED,
    STATUS_RUNNING,
    get_task,
    update_task,
)
from edim_dde_ai.hitl import is_hitl_waiting
from edim_dde_ai.observability import build_run_config
from edim_dde_ai.session.host import attach_thread_id, memory_enabled_for_agent
from edim_dde_api.request_context import reset_request_id, set_request_id
from edim_dde_domain.sources import (
    reset_request_databricks_token,
    set_request_databricks_token,
)

logger = logging.getLogger(__name__)

ENV_WORKER_THREADS = "EDIM_A2A_WORKER_THREADS"

_EXECUTOR: ThreadPoolExecutor | None = None
_EXEC_LOCK = __import__("threading").Lock()


def _executor() -> ThreadPoolExecutor:
    global _EXECUTOR
    with _EXEC_LOCK:
        if _EXECUTOR is None:
            raw = (os.environ.get(ENV_WORKER_THREADS) or "4").strip()
            try:
                workers = max(1, int(raw))
            except ValueError:
                workers = 4
            _EXECUTOR = ThreadPoolExecutor(
                max_workers=workers, thread_name_prefix="edim-a2a"
            )
        return _EXECUTOR


def shutdown_a2a_workers(*, wait: bool = False) -> None:
    """Shut down the worker pool (tests / process exit)."""
    global _EXECUTOR
    with _EXEC_LOCK:
        if _EXECUTOR is not None:
            _EXECUTOR.shutdown(wait=wait, cancel_futures=False)
            _EXECUTOR = None


def schedule_agent_task(
    task_id: str,
    *,
    databricks_token: str | None = None,
) -> None:
    """Queue background execution for an accepted task."""
    _executor().submit(run_agent_task, task_id, databricks_token)


def run_agent_task(task_id: str, databricks_token: str | None = None) -> dict[str, Any]:
    """Execute one task synchronously; update store. Returns final record."""
    rec = get_task(task_id)
    if rec is None:
        logger.warning("a2a worker missing task_id=%s", task_id)
        return {}

    aid = str(rec.get("agent_id") or "")
    rid = str(rec.get("request_id") or "")
    cid = rec.get("conversation_id")
    payload = dict(rec.get("payload") or {})
    update_task(task_id, status=STATUS_RUNNING, error=None)

    tok_ctx = set_request_databricks_token(databricks_token) if databricks_token else None
    rid_ctx = set_request_id(rid) if rid else None
    try:
        config = build_run_config(
            agent_id=aid,
            request_id=rid,
            metadata={"edim_a2a": True, "task_id": task_id},
        )
        if cid and memory_enabled_for_agent(aid):
            config = attach_thread_id(config, str(cid))
            payload.setdefault("thread_id", str(cid))
        if cid:
            payload.setdefault("conversation_id", str(cid))
        payload.setdefault("request_id", rid)
        payload["task_id"] = task_id

        final = create_agent(aid).invoke(payload, config=config)
        state = dict(final or {})
        if is_hitl_waiting(state):
            status = STATUS_INPUT_NEEDED
        else:
            status = STATUS_COMPLETED
        updated = update_task(
            task_id,
            status=status,
            state=state,
            error=None,
            session_id=state.get("session_id"),
        )
        return updated or {}
    except Exception as exc:  # noqa: BLE001 — persist failure on task
        logger.exception("a2a worker failed task_id=%s agent=%s", task_id, aid)
        updated = update_task(
            task_id,
            status=STATUS_ERROR,
            error=str(exc)[:800],
            state={"error": str(exc)[:800], "task_id": task_id},
        )
        return updated or {}
    finally:
        if rid_ctx is not None:
            reset_request_id(rid_ctx)
        if tok_ctx is not None:
            reset_request_databricks_token(tok_ctx)
