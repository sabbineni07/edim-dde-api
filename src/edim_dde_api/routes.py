"""HTTP routes: thin wrappers around edim_dde_ai.create_agent().invoke()."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from typing import Any, TypeVar

from edim_dde_ai import create_agent, list_agents
from edim_dde_ai.observability import build_run_config, get_observability_provider
from edim_dde_ai.retrieval import get_retrieval_provider, provider_for_corpus
from edim_dde_ai.store import get_state_store
from edim_dde_domain.errors import (
    DatabricksNotConfiguredError,
    DomainToolError,
    NoJobMetricsError,
)
from edim_dde_domain.sources import (
    extract_forwarded_databricks_token,
    get_request_databricks_token,
    is_databricks_apps_runtime,
    reset_request_databricks_token,
    set_request_databricks_token,
)
from fastapi import APIRouter, Header, HTTPException, Request

from edim_dde_api import __version__
from edim_dde_api.schemas import (
    KnowledgeIngestRequest,
    KnowledgeIngestResponse,
    RcaRequest,
    RcaResponse,
    TuningRequest,
    TuningResponse,
    rca_response_from_agent_state,
    tuning_response_from_agent_state,
)

router = APIRouter()
api_v1 = APIRouter(prefix="/api/v1")

T = TypeVar("T")


def _request_id(
    request: Request,
    x_request_id: str | None,
) -> str:
    return (x_request_id or request.headers.get("x-request-id") or "").strip() or str(
        uuid.uuid4()
    )


async def _invoke_agent_in_thread(
    request: Request,
    fn: Callable[[], T],
) -> T:
    """Run agent work in a worker thread with Apps user token bound.

    Re-binds ``X-Forwarded-Access-Token`` inside the thread so SQL auth does
    not depend on ContextVar surviving BaseHTTPMiddleware / TaskGroup hops.
    """
    token = extract_forwarded_databricks_token(request.headers)

    def _run() -> T:
        ctx = set_request_databricks_token(token) if token else None
        try:
            return fn()
        finally:
            if ctx is not None:
                reset_request_databricks_token(ctx)

    return await asyncio.to_thread(_run)


@router.get("/health")
def health() -> dict[str, Any]:
    obs = get_observability_provider()
    store = get_state_store()
    retrieval = get_retrieval_provider()
    return {
        "status": "ok",
        "agents": list_agents(),
        "version": __version__,
        "observability": getattr(obs, "name", "unknown"),
        "state_store": getattr(store, "name", "unknown"),
        "retrieval": getattr(retrieval, "name", "unknown"),
    }


@api_v1.post("/knowledge/ingest", response_model=KnowledgeIngestResponse)
async def ingest_knowledge(body: KnowledgeIngestRequest) -> KnowledgeIngestResponse:
    """Curated document upsert into the active retrieval backend.

    Requires ``accepted=true`` (Acceptance gate). Platform Jobs remain the
    primary bulk ingest path; this endpoint is for human-approved summaries.
    """
    if not body.accepted:
        raise HTTPException(
            status_code=400,
            detail="accepted=true is required before indexing (Acceptance gate)",
        )
    text = (body.text or "").strip()
    summary = (body.summary or "").strip()
    if summary:
        text = f"Summary: {summary}\n\n{text}".strip()
    if not text:
        raise HTTPException(status_code=400, detail="text or summary is required")

    provider = provider_for_corpus(body.corpus)
    try:
        provider.upsert(
            corpus=body.corpus,
            doc_id=body.doc_id,
            text=text,
            metadata=dict(body.metadata or {}),
            source=body.source,
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return KnowledgeIngestResponse(
        status="indexed",
        corpus=body.corpus,
        doc_id=body.doc_id,
        retrieval=getattr(provider, "name", "unknown"),
    )


@api_v1.get("/debug/sql-auth")
def debug_sql_auth(request: Request) -> dict[str, Any]:
    """Non-secret SQL auth diagnostics for Apps bring-up (no token values)."""
    forwarded = extract_forwarded_databricks_token(request.headers)
    scoped = get_request_databricks_token()
    return {
        "apps_runtime": is_databricks_apps_runtime(),
        "forwarded_access_token_present": bool(forwarded),
        "request_scoped_token_present": bool(scoped),
        "hint": (
            "On Apps, forwarded_access_token_present must be true for live SQL. "
            "Add User authorization scope `sql`, bind the warehouse, re-consent "
            "the app, and call via the App URL while signed into the workspace."
        ),
    }


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
        payload = body.model_dump()
        final = await _invoke_agent_in_thread(
            request, lambda: agent.invoke(payload, config=config)
        )
        return rca_response_from_agent_state(final)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except DatabricksNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DomainToolError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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
        payload = body.model_dump()
        final = await _invoke_agent_in_thread(
            request, lambda: agent.invoke(payload, config=config)
        )
        return tuning_response_from_agent_state(final)
    except NoJobMetricsError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DatabricksNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DomainToolError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
