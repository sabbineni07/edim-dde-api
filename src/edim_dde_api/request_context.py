"""Request-scoped correlation id for structured logging.

Business purpose
----------------
Propagate a per-request ``request_id`` via ContextVar so logs from handlers,
worker threads, and domain SQL can be correlated. Middleware and route helpers
bind/reset the id; ``configure_request_id_logging`` wires it into formatters.

Public API
----------
* ``get_request_id`` / ``set_request_id`` / ``reset_request_id`` — ContextVar accessors
* ``RequestIdFilter`` — logging filter that injects ``record.request_id``
* ``configure_request_id_logging`` — install filter + format once at startup
"""

from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from typing import Optional

_request_id: ContextVar[Optional[str]] = ContextVar("edim_request_id", default=None)


def get_request_id() -> Optional[str]:
    """Return the bound request id, or ``None`` when unbound.

    Returns:
        Current ContextVar value (stripped at set time), or ``None``.
    """
    return _request_id.get()


def set_request_id(value: Optional[str]) -> Token:
    """Bind a request id for the current context.

    Empty / whitespace-only values clear the binding (store ``None``).

    Args:
        value: Incoming ``X-Request-Id`` or generated UUID string.

    Returns:
        ContextVar token for ``reset_request_id`` in a ``finally`` block.
    """
    return _request_id.set((value or "").strip() or None)


def reset_request_id(token: Token) -> None:
    """Restore the previous ContextVar state after the request finishes.

    Args:
        token: Token returned by ``set_request_id``.
    """
    _request_id.reset(token)


class RequestIdFilter(logging.Filter):
    """Inject ``request_id`` onto every LogRecord (empty string when unbound).

    Attributes:
        (none) — reads ``get_request_id()`` per record; unbound → ``"-"``.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Attach ``request_id`` and always allow the record through.

        Args:
            record: Log record being emitted.

        Returns:
            Always ``True`` (filter does not drop records).
        """
        rid = get_request_id()
        record.request_id = rid or "-"  # type: ignore[attr-defined]
        return True


_CONFIGURED = False


def configure_request_id_logging() -> None:
    """Install filter + ensure format includes request_id (once).

    Idempotent: subsequent calls no-op. Attaches to the root logger and common
    library loggers so request ids appear even when handlers bypass root filters.
    """
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
