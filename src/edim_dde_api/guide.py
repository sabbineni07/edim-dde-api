"""Engineer MkDocs site at ``/guide/``.

Business purpose
----------------
Serve built HTML (``index.html``) from FastAPI ``StaticFiles``.

* Docker / laptop: mount when a site dir exists.
* Databricks Apps: **off** unless ``EDIM_MOUNT_GUIDE=1`` (Apps always sets
  ``DATABRICKS_APP_PORT``). Ship ``guide-site/`` next to ``app.yaml``.

Public API
----------
* ``resolve_guide_site_dir`` / ``mount_guide``
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)


def _env_on(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _site_candidates() -> list[Path]:
    """Directories that may contain MkDocs ``index.html``."""
    paths: list[Path] = []
    cwd = Path.cwd()
    env = (os.environ.get("EDIM_GUIDE_SITE_DIR") or "").strip()
    if env:
        site = Path(env).expanduser()
        if not site.is_absolute():
            site = cwd / site
        paths.append(site)
    # Apps bundle: folder next to app.yaml (process cwd is the app source root)
    paths.append(cwd / "guide-site")
    here = Path(__file__).resolve()
    # Installed wheel: .../site-packages/edim_dde_api/guide.py - not the repo
    api_root = here.parents[2]
    paths.append(api_root / "deploy" / "docker" / "guide-site")
    paths.append(api_root.parent / "edim-dde-domain" / "site")
    return paths


def guide_diagnostics() -> dict[str, object]:
    """Non-secret status for ``/api/v1/debug/guide`` (Apps bring-up)."""
    on_apps = bool((os.environ.get("DATABRICKS_APP_PORT") or "").strip())
    mount_opt_in = _env_on("EDIM_MOUNT_GUIDE")
    candidates: list[dict[str, object]] = []
    resolved: str | None = None
    for path in _site_candidates():
        index = path / "index.html"
        entry: dict[str, object] = {
            "path": str(path),
            "index_exists": index.is_file(),
        }
        if index.is_file() and resolved is None:
            resolved = str(path.resolve())
        candidates.append(entry)

    blocked_on_apps = on_apps and not mount_opt_in
    mounted = resolved is not None and not blocked_on_apps
    return {
        "mounted": mounted,
        "apps_runtime": on_apps,
        "edim_mount_guide": mount_opt_in,
        "edim_guide_site_dir": (os.environ.get("EDIM_GUIDE_SITE_DIR") or "").strip() or None,
        "cwd": os.getcwd(),
        "resolved_site_dir": resolved,
        "candidates": candidates,
        "hint": (
            "Copy deploy/docker/guide-site to deploy/databricks-app/guide-site before "
            "apps-sync; set EDIM_MOUNT_GUIDE=1 in app.yaml; rebuild vendor wheels "
            "after guide.py changes; open /guide/ (trailing slash)."
        ),
    }


def resolve_guide_site_dir() -> Path | None:
    """Return a directory containing ``index.html``, or ``None``.

    On Databricks Apps, returns ``None`` unless ``EDIM_MOUNT_GUIDE`` is truthy.
    """
    on_apps = bool((os.environ.get("DATABRICKS_APP_PORT") or "").strip())
    if on_apps and not _env_on("EDIM_MOUNT_GUIDE"):
        logger.info(
            "Engineer guide skipped on Databricks Apps "
            "(set EDIM_MOUNT_GUIDE=1 and include guide-site/index.html)"
        )
        return None

    for path in _site_candidates():
        index = path / "index.html"
        if index.is_file():
            return path.resolve()
    logger.info(
        "Engineer guide not found. Tried: %s cwd=%s",
        [str(p) for p in _site_candidates()],
        os.getcwd(),
    )
    return None


def mount_guide(app: FastAPI) -> None:
    """Mount ``/guide`` when ``resolve_guide_site_dir`` finds a site."""
    site = resolve_guide_site_dir()
    if site is None:
        return
    app.mount(
        "/guide",
        StaticFiles(directory=str(site), html=True),
        name="guide",
    )
    logger.info("Engineer guide mounted at /guide/ from %s", site)
