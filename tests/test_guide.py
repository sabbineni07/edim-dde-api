"""MkDocs Material static guide mount."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_mount_guide_serves_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(
        "<html><body><h1>MkDocs Home</h1></body></html>", encoding="utf-8"
    )
    sub = site / "platform" / "key-vault"
    sub.mkdir(parents=True)
    (sub / "index.html").write_text(
        "<html><body>Key Vault page</body></html>", encoding="utf-8"
    )
    monkeypatch.setenv("EDIM_GUIDE_SITE_DIR", str(site))
    monkeypatch.delenv("DATABRICKS_APP_PORT", raising=False)

    from edim_dde_api.guide import mount_guide

    app = FastAPI()
    mount_guide(app)
    client = TestClient(app)
    res = client.get("/guide/")
    assert res.status_code == 200
    assert "MkDocs Home" in res.text
    res2 = client.get("/guide/platform/key-vault/")
    assert res2.status_code == 200
    assert "Key Vault page" in res2.text


def test_guide_not_mounted_on_databricks_apps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setenv("EDIM_GUIDE_SITE_DIR", str(site))
    monkeypatch.setenv("DATABRICKS_APP_PORT", "8080")

    from edim_dde_api.guide import mount_guide, resolve_guide_site_dir

    assert resolve_guide_site_dir() is None
    app = FastAPI()
    mount_guide(app)
    client = TestClient(app)
    res = client.get("/guide/")
    assert res.status_code == 404


def test_guide_mounted_on_apps_when_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<html><body>apps-guide</body></html>", encoding="utf-8")
    monkeypatch.setenv("EDIM_GUIDE_SITE_DIR", str(site))
    monkeypatch.setenv("DATABRICKS_APP_PORT", "8080")
    monkeypatch.setenv("EDIM_MOUNT_GUIDE", "1")

    from edim_dde_api.guide import mount_guide

    app = FastAPI()
    mount_guide(app)
    client = TestClient(app)
    res = client.get("/guide/")
    assert res.status_code == 200
    assert "apps-guide" in res.text


def test_guide_diagnostics_reports_mount_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setenv("EDIM_GUIDE_SITE_DIR", str(site))
    monkeypatch.setenv("DATABRICKS_APP_PORT", "8080")
    monkeypatch.setenv("EDIM_MOUNT_GUIDE", "1")

    from edim_dde_api.guide import guide_diagnostics

    info = guide_diagnostics()
    assert info["mounted"] is True
    assert info["apps_runtime"] is True
    assert info["resolved_site_dir"] == str(site.resolve())
