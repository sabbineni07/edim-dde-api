"""edim-dde-api — FastAPI host for edim-dde-domain YAML agents.

Business purpose
----------------
Thin HTTP layer over ``edim-dde-domain`` agents (Spark RCA + cluster tuning).
Boots pluggable planes (LLM, state store, retrieval, observability) and exposes
REST under ``/api/v1`` plus ``/health`` and an optional local engineer guide.

Public API
----------
* ``__version__`` — package version string (also surfaced in OpenAPI / health)
"""

__version__ = "1.0.0"
