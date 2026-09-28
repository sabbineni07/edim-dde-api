"""A2A async task helpers — re-export store + schedule worker.

Business purpose
----------------
API routes accept async invokes and poll task status. Persistence lives in
``edim_dde_ai.a2a.tasks``; execution is ``a2a_worker`` (in-process pool).
"""

from __future__ import annotations

from edim_dde_ai.a2a.tasks import (
    STATUS_COMPLETED,
    STATUS_ERROR,
    STATUS_INPUT_NEEDED,
    STATUS_RUNNING,
    accept_task,
    clear_a2a_tasks,
    configure_task_store_from_env,
    get_task,
    get_task_store,
    set_task_store,
    update_task,
)
from edim_dde_api.a2a_worker import schedule_agent_task, shutdown_a2a_workers

__all__ = [
    "STATUS_COMPLETED",
    "STATUS_ERROR",
    "STATUS_INPUT_NEEDED",
    "STATUS_RUNNING",
    "accept_task",
    "clear_a2a_tasks",
    "configure_task_store_from_env",
    "get_task",
    "get_task_store",
    "schedule_agent_task",
    "set_task_store",
    "shutdown_a2a_workers",
    "update_task",
]
