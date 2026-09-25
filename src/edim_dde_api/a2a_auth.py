"""Interim A2A AuthZ for generic invoke (precursor to BL-056).

When ``EDIM_A2A_TOKEN`` is set, ``POST /api/v1/agents/{id}/invoke`` (and
directory register) require a matching Bearer token or ``X-Edim-A2A-Token``.
When unset, requests are allowed (local/dev default).
"""

from __future__ import annotations

import os
import secrets
from typing import Annotated

from fastapi import Header, HTTPException

ENV_A2A_TOKEN = "EDIM_A2A_TOKEN"


def a2a_token_configured() -> bool:
    """True when inbound A2A auth is enforced."""
    return bool((os.environ.get(ENV_A2A_TOKEN) or "").strip())


def require_a2a_token(
    authorization: Annotated[str | None, Header()] = None,
    x_edim_a2a_token: Annotated[str | None, Header(alias="X-Edim-A2A-Token")] = None,
) -> None:
    """FastAPI dependency: enforce shared A2A token when configured.

    Raises:
        HTTPException: 401 when token required and missing/wrong.
    """
    expected = (os.environ.get(ENV_A2A_TOKEN) or "").strip()
    if not expected:
        return

    provided = (x_edim_a2a_token or "").strip()
    if not provided and authorization:
        raw = authorization.strip()
        if raw.lower().startswith("bearer "):
            provided = raw[7:].strip()
        else:
            provided = raw

    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=401,
            detail=(
                "A2A token required. Send Authorization: Bearer <EDIM_A2A_TOKEN> "
                "or X-Edim-A2A-Token (interim AuthZ; full SSO is BL-056)."
            ),
            headers={"WWW-Authenticate": "Bearer"},
        )
