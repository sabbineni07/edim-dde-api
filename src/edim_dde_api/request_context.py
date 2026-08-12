"""Request-scoped correlation id for structured logging."""

from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from typing import Optional

_request_id: ContextVar[Optional[str]] = ContextVar("edim_request_id", default=None)


def get_request_id() -> Optional[str]:
    return _request_id.get()


def set_request_id(value: Optional[str]) -> Token:
    return _request_id.set((value or "").strip() or None)


def reset_request_id(token: Token) -> None:
    _request_id.reset(token)


class RequestIdFilter(logging.Filter):
    """Inject ``request_id`` onto every LogRecord (empty string when unbound)."""

    def filter(self, record: logging.LogRecord) -> bool:
        rid = get_request_id()
        record.request_id = rid or "-"  # type: ignore[attr-defined]
        return True


_CONFIGURED = False


def configure_request_id_logging() -> None:
    """Install filter + ensure format includes request_id (once)."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    root = logging.getLogger()
    filt = RequestIdFilter()
    root.addFilter(filt)
    for handler in root.handlers:
        handler.addFilter(filt)
        # Prefer existing formatters that already mention request_id
        fmt = handler.formatter
        if fmt is None:
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s %(levelname)s [%(name)s] "
                    "[request_id=%(request_id)s] %(message)s"
                )
            )
        else:
            # Rebuild with request_id if missing
            style = getattr(fmt, "_style", None)
            fmt_str = getattr(style, "_fmt", None) if style is not None else None
            if isinstance(fmt_str, str) and "request_id" not in fmt_str:
                handler.setFormatter(
                    logging.Formatter(
                        fmt_str + " [request_id=%(request_id)s]"
                        if fmt_str
                        else "%(levelname)s [request_id=%(request_id)s] %(message)s"
                    )
                )
    # Also attach to common library loggers if they bypass root filters oddly
    for name in ("edim_dde_api", "edim_dde_domain", "edim_dde_ai", "uvicorn", "uvicorn.error"):
        logging.getLogger(name).addFilter(filt)
    _CONFIGURED = True
