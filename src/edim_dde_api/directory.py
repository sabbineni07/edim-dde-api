"""Agent Directory HTTP helpers — thin wrap of ``edim_dde_ai.a2a.bindings``.

Kept for route imports; binding merge logic lives in the framework (ADR-001).
"""

from __future__ import annotations

from typing import Any

from edim_dde_ai.a2a.bindings import (
    clear_runtime_bindings,
    get_binding,
    list_bindings,
    register_runtime_binding,
    resolve_env_label,
)

# Back-compat aliases used by routes / tests
resolve_directory_env = resolve_env_label
list_agent_bindings = list_bindings
get_agent_binding = get_binding


def register_agent_binding(binding: dict[str, Any]) -> dict[str, Any]:
    """Upsert a runtime directory binding (heartbeat / register)."""
    return register_runtime_binding(binding)


__all__ = [
    "clear_runtime_bindings",
    "get_agent_binding",
    "list_agent_bindings",
    "register_agent_binding",
    "resolve_directory_env",
]
