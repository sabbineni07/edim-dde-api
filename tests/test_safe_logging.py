"""Safe logging redacts secrets/PII and preserves stack text."""

from __future__ import annotations

import logging

from edim_dde_api.safe_logging import (
    format_exception_safe,
    log_exception_once,
    redact_secrets_and_pii,
    safe_exc_message,
)


def test_redact_bearer_and_jwt():
    jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    text = f"Authorization: Bearer abcdefghijklmnop {jwt}"
    out = redact_secrets_and_pii(text)
    assert "Authorization: [REDACTED]" in out or "Bearer [REDACTED]" in out
    assert "eyJhbGci" not in out
    assert "[REDACTED:jwt]" in out


def test_redact_client_secret_label():
    out = redact_secrets_and_pii("client_secret=super-secret-value password=hunter2")
    assert "super-secret-value" not in out
    assert "hunter2" not in out
    assert "[REDACTED]" in out


def test_format_exception_safe_includes_traceback_without_secret():
    try:
        raise RuntimeError("token=Bearer eyJhbGciOiJIUzI1NiJ9.aaa.bbb leaked")
    except RuntimeError as exc:
        text = format_exception_safe(exc)
    assert "Traceback" in text
    assert "eyJhbGci" not in text
    assert "RuntimeError" in text


def test_log_exception_once_writes_redacted_stack(caplog):
    caplog.set_level(logging.ERROR)
    log = logging.getLogger("edim_dde_api.test_safe")
    try:
        raise ValueError("api_key=abcd1234")
    except ValueError as exc:
        log_exception_once(log, "unit-test failure", exc)
    assert any("unit-test failure" in r.message for r in caplog.records)
    joined = "\n".join(r.message for r in caplog.records)
    assert "abcd1234" not in joined
    assert "Traceback" in joined
    assert "ValueError" in safe_exc_message(ValueError("x"))
