"""Re-export domain agent bootstrap for API hosts.

Business purpose
----------------
Convenience import so API / deployment entrypoints can call
``bootstrap_agents`` without depending on the deeper ``edim_dde_domain``
layout. The real registration logic lives in the domain package.

Public API
----------
* ``bootstrap_agents`` — idempotent YAML agent + node registration
  (re-exported from ``edim_dde_domain``)
"""

from __future__ import annotations

from edim_dde_domain import bootstrap_agents

__all__ = ["bootstrap_agents"]
