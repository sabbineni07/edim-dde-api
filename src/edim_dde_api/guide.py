"""Local Docker / laptop engineer guide via MkDocs Material static site.

Not deployed to Databricks Apps. Build with ``make guide-site`` (or
``make vendor-wheels``), then open ``http://127.0.0.1:8080/guide/``.

Material theme provides sidebar nav + Previous / Next from ``mkdocs.yml``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)


def resolve_guide_site_dir() -> Path | None:
    """Return built MkDocs ``site/`` directory if present."""
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
    """Mount MkDocs static site at ``/guide`` when available."""
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
