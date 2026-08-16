"""FastAPI middleware: bind per-request Databricks user OAuth + request id.

Business purpose
----------------
Ensure every request has (1) an Apps-forwarded Databricks user token available
to domain SQL via ContextVar, and (2) a stable ``X-Request-Id`` for logging and
response echo. Runs ahead of route handlers; worker threads re-bind via
``routes._invoke_agent_in_thread``.

Public API
----------
* ``DatabricksUserTokenMiddleware`` — bind ``X-Forwarded-Access-Token``
* ``RequestIdMiddleware`` — bind / generate request id + set response header
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from edim_dde_api.request_context import reset_request_id, set_request_id
from edim_dde_domain.sources import (
    extract_forwarded_databricks_token,
    reset_request_databricks_token,
    set_request_databricks_token,
)


class DatabricksUserTokenMiddleware(BaseHTTPMiddleware):
    """Store forwarded Apps user OAuth in a ContextVar for the request lifetime.

    Reads ``X-Forwarded-Access-Token`` (or equivalent) from headers. When absent
    (local laptop without Apps), the ContextVar stays unbound and domain SQL
    falls back to configured service principal / PAT sources.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Bind token for the ASGI call stack, then reset in ``finally``.

        Args:
            request: Incoming Starlette request.
            call_next: Next middleware / route in the chain.

        Returns:
            Downstream response unchanged.
        """
        token = extract_forwarded_databricks_token(request.headers)
        ctx = set_request_databricks_token(token) if token else None
        try:
            return await call_next(request)
        finally:
            if ctx is not None:
                reset_request_databricks_token(ctx)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Bind ``X-Request-Id`` (or generate one) for logging + response echo.

    Prefers the client-supplied header; otherwise assigns a UUID. Stores the
    value on ``request.state.request_id``, the ContextVar, and the response
    ``X-Request-Id`` header so clients can correlate.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Resolve request id, bind context, echo header on the response.

        Args:
            request: Incoming Starlette request.
            call_next: Next middleware / route in the chain.

        Returns:
            Downstream response with ``X-Request-Id`` set.
        """
        rid = (
            request.headers.get("x-request-id")
            or request.headers.get("X-Request-Id")
            or ""
        ).strip() or str(uuid.uuid4())
        request.state.request_id = rid
        token = set_request_id(rid)
        try:
            response = await call_next(request)
        finally:
            reset_request_id(token)
        response.headers["X-Request-Id"] = rid
        return response
