"""Local Docker / laptop engineer guide via MkDocs Material static site.

Business purpose
----------------
Serve the MkDocs-built engineer guide at ``/guide/`` for local and Docker
development. Intentionally **not** mounted on Databricks Apps (detected via
``DATABRICKS_APP_PORT``). Build with ``make guide-site`` (or ``make vendor-wheels``).

Public API
----------
* ``resolve_guide_site_dir`` — locate built ``site/`` if present
* ``mount_guide`` — attach StaticFiles at ``/guide`` when a site exists
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)


def resolve_guide_site_dir() -> Path | None:
    """Return built MkDocs ``site/`` directory if present.

    Search order: ``EDIM_GUIDE_SITE_DIR``, Docker vendor path under the API
    package, then editable ``edim-dde-domain/site``. Returns ``None`` on Apps
    runtime or when no ``index.html`` is found.

    Returns:
        Absolute path to a directory containing ``index.html``, or ``None``.
    """
    if (os.environ.get("DATABRICKS_APP_PORT") or "").strip():
        return None

    candidates: list[Path] = []
    env = (os.environ.get("EDIM_GUIDE_SITE_DIR") or "").strip()
    if env:
        candidates.append(Path(env).expanduser())

    here = Path(__file__).resolve()
    api_root = here.parents[2]
    candidates.append(api_root / "deploy" / "docker" / "guide-site")
    # Editable: domain mkdocs default site_dir
    candidates.append(api_root.parent / "edim-dde-domain" / "site")

    for path in candidates:
        if (path / "index.html").is_file():
            return path.resolve()
    return None


def mount_guide(app: FastAPI) -> None:
    """Mount MkDocs static site at ``/guide`` when available.

    Args:
        app: FastAPI application to attach the StaticFiles mount to.

    Returns:
        None. Logs info whether the guide was mounted or skipped.
    """
    site = resolve_guide_site_dir()
    if site is None:
        logger.info(
            "Engineer guide not mounted (build with: make guide-site; "
            "Docker sets EDIM_GUIDE_SITE_DIR=/app/guide-site)"
        )
        return
    app.mount(
        "/guide",
        StaticFiles(directory=str(site), html=True),
        name="guide",
    )
    logger.info("Engineer guide mounted at /guide/ from %s", site)
