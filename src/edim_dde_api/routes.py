"""HTTP routes: thin wrappers around edim_dde_ai.create_agent().invoke()."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from edim_dde_ai import create_agent, list_agents
from edim_dde_ai.observability import build_run_config
from edim_dde_domain.errors import DatabricksNotConfiguredError, NoJobMetricsError
from fastapi import APIRouter, Header, HTTPException, Request

from edim_dde_api import __version__
from edim_dde_api.schemas import (
    RcaRequest,
    RcaResponse,
    TuningRequest,
    TuningResponse,
    rca_response_from_agent_state,
    tuning_response_from_agent_state,
)

router = APIRouter()
api_v1 = APIRouter(prefix="/api/v1")


def _request_id(
    request: Request,
    x_request_id: str | None,
) -> str:
    return (x_request_id or request.headers.get("x-request-id") or "").strip() or str(
        uuid.uuid4()
    )


@router.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "agents": list_agents(), "version": __version__}


@api_v1.post("/rca/analyze", response_model=RcaResponse)
async def analyze_rca(
    body: RcaRequest,
    request: Request,
    x_request_id: str | None = Header(default=None),
) -> RcaResponse:
    """Run the spark_rca YAML agent end-to-end."""
    rid = _request_id(request, x_request_id)
    try:
        agent = create_agent("spark_rca")
        config = build_run_config(agent_id="spark_rca", request_id=rid)
        final = await asyncio.to_thread(
            lambda: agent.invoke(body.model_dump(), config=config)
        )
        return rca_response_from_agent_state(final)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except DatabricksNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@api_v1.post("/recommendations", response_model=TuningResponse)
async def recommend_cluster(
    body: TuningRequest,
    request: Request,
    x_request_id: str | None = Header(default=None),
) -> TuningResponse:
    """Run the cluster_tuning YAML agent end-to-end."""
    rid = _request_id(request, x_request_id)
    try:
        agent = create_agent("cluster_tuning")
        config = build_run_config(agent_id="cluster_tuning", request_id=rid)
        final = await asyncio.to_thread(
            lambda: agent.invoke(body.model_dump(), config=config)
        )
        return tuning_response_from_agent_state(final)
    except NoJobMetricsError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DatabricksNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
