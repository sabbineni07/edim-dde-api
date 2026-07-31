"""HTTP routes: thin wrappers around edim_dde_ai.create_agent().invoke()."""

from __future__ import annotations

import asyncio
from typing import Any

from edim_dde_ai import create_agent, list_agents
from edim_dde_domain.errors import DatabricksNotConfiguredError, NoJobMetricsError
from fastapi import APIRouter, HTTPException

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


@router.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "agents": list_agents()}


@api_v1.post("/rca/analyze", response_model=RcaResponse)
async def analyze_rca(body: RcaRequest) -> RcaResponse:
    """Run the spark_rca YAML agent end-to-end."""
    try:
        agent = create_agent("spark_rca")
        final = await asyncio.to_thread(agent.invoke, body.model_dump())
        return rca_response_from_agent_state(final)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except DatabricksNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@api_v1.post("/recommendations", response_model=TuningResponse)
async def recommend_cluster(body: TuningRequest) -> TuningResponse:
    """Run the cluster_tuning YAML agent end-to-end."""
    try:
        agent = create_agent("cluster_tuning")
        final = await asyncio.to_thread(agent.invoke, body.model_dump())
        return tuning_response_from_agent_state(final)
    except NoJobMetricsError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DatabricksNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
