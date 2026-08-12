"""Request-id correlation logging + response header."""

from __future__ import annotations

import logging

from fastapi.testclient import TestClient


def test_request_id_echoed_on_health(monkeypatch):
    # Avoid Key Vault / Foundry noise at import lifespan where possible
    monkeypatch.setenv("EDIM_STRICT_STARTUP", "0")
    from edim_dde_api.main import app
    from edim_dde_api.request_context import configure_request_id_logging

    configure_request_id_logging()
    client = TestClient(app)
    res = client.get("/health", headers={"X-Request-Id": "corr-test-001"})
    assert res.status_code == 200
    assert res.headers.get("X-Request-Id") == "corr-test-001"


def test_request_id_filter_binds_record():
    from edim_dde_api.request_context import (
        RequestIdFilter,
        reset_request_id,
        set_request_id,
    )

    filt = RequestIdFilter()
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    tok = set_request_id("abc-123")
    try:
        assert filt.filter(record) is True
        assert record.request_id == "abc-123"  # type: ignore[attr-defined]
    finally:
        reset_request_id(tok)
