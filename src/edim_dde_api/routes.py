"""HTTP routes: thin wrappers around edim_dde_ai.create_agent().invoke()."""

from __future__ import annotations

from typing import Any

from edim_dde_ai import create_agent, list_agents
from edim_dde_domain.errors import DatabricksNotConfiguredError, NoJobMetricsError
from fastapi import APIRouter, HTTPException

from edim_dde_api.schemas import RcaRequest, TuningRequest

router = APIRouter()


@router.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "agents": list_agents()}


@router.post("/api/rca/analyze")
def analyze_rca(body: RcaRequest) -> dict[str, Any]:
    """Run the spark_rca YAML agent end-to-end."""
    try:
        agent = create_agent("spark_rca")
        final = agent.invoke(body.model_dump())
    except DatabricksNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return final.get("result") or final


@router.post("/api/recommendations")
def recommend_cluster(body: TuningRequest) -> dict[str, Any]:
    """Run the cluster_tuning YAML agent end-to-end."""
    try:
        agent = create_agent("cluster_tuning")
        final = agent.invoke(body.model_dump())
    except NoJobMetricsError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DatabricksNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "job_id": final.get("job_id"),
        "cluster_id": final.get("cluster_id"),
        "job_run_id": final.get("job_run_id"),
        "recommendation": final.get("recommendation") or {},
        "risk_assessment": final.get("risk_assessment") or {},
        "pattern_analysis": final.get("pattern_analysis") or "",
        "explanation": final.get("explanation") or "",
    }
