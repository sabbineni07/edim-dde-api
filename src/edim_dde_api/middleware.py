"""FastAPI middleware: bind per-request Databricks user OAuth + request id."""

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
    """Store forwarded Apps user OAuth in a ContextVar for the request lifetime."""

    async def dispatch(self, request: Request, call_next) -> Response:
        token = extract_forwarded_databricks_token(request.headers)
        ctx = set_request_databricks_token(token) if token else None
        try:
            return await call_next(request)
        finally:
            if ctx is not None:
                reset_request_databricks_token(ctx)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Bind ``X-Request-Id`` (or generate one) for logging + response echo."""

    async def dispatch(self, request: Request, call_next) -> Response:
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
