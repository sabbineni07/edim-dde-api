"""Safe exception logging: stack traces without tokens / secrets / PII.

Log **once** at the HTTP (or lifespan) boundary when mapping failures to
responses. Do not also log the same failure in nested helpers.
"""

from __future__ import annotations

import logging
import re
import traceback
from typing import Any

from edim_dde_domain.security.pii import redact_text

# Applied in order; keep capture groups so we preserve labels and redact values.
_SECRET_SUBS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9\-._~+/]+=*"),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"(?i)(authorization\s*[:=]\s*)\S+"),
        r"\1[REDACTED]",
    ),
    (
        re.compile(
            r"(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|"
            r"client[_-]?secret|password|passwd|secret|"
            r"x-forwarded-access-token)\s*[:=]\s*)\S+"
        ),
        r"\1[REDACTED]",
    ),
    (
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
        ),
        "[REDACTED:jwt]",
    ),
    (
        re.compile(r"(?i)((?:SharedAccessSignature|sig)=)[^\s;&]+"),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"(?i)((?:AccountKey|Password|pwd)=)[^\s;]+"),
        r"\1[REDACTED]",
    ),
)


def redact_secrets_and_pii(text: str) -> str:
    """Redact credentials then PII patterns from arbitrary text."""
    if not text:
        return text
    out = text
    for pat, repl in _SECRET_SUBS:
        out = pat.sub(repl, out)
    return redact_text(out)


def format_exception_safe(exc: BaseException) -> str:
    """Full traceback text with secrets/PII scrubbed (includes __cause__ chain)."""
    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return redact_secrets_and_pii(text)


def safe_exc_message(exc: BaseException, *, limit: int = 500) -> str:
    """Short redacted ``type: message`` for log summaries / client detail."""
    msg = redact_secrets_and_pii(f"{type(exc).__name__}: {exc}")
    if len(msg) > limit:
        return msg[: limit - 3] + "..."
    return msg


def log_exception_once(
    logger: logging.Logger,
    message: str,
    exc: BaseException,
    *,
    level: int = logging.ERROR,
) -> None:
    """Log ``message`` + redacted stack once. Prefer this over ``logger.exception``.

    Formats the traceback ourselves so redaction applies to the whole stack
    (``logger.exception`` would emit an unretracted traceback).
    """
    stack = format_exception_safe(exc)
    logger.log(level, "%s | %s\n%s", message, safe_exc_message(exc), stack)
