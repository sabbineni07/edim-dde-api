"""HTTP routes: thin wrappers around edim_dde_ai.create_agent().invoke().

Business purpose
----------------
Expose Spark RCA and cluster-tuning YAML agents as REST, plus health,
curated knowledge ingest, and recommendation lifecycle (list/get/patch).
Handlers bind request id + Apps user token into worker threads, map agent
state to Pydantic responses, and best-effort persist to RecommendationStore.

Public API / endpoint groups
----------------------------
* ``router`` — ``GET /health`` (unversioned)
* ``api_v1`` — prefix ``/api/v1``:
  - Knowledge — ``POST /knowledge/ingest``
  - Debug — ``GET /debug/sql-auth``
  - RCA — ``POST /rca/analyze``, recommendation list/get/patch
  - Cluster tuning — ``POST /cluster_tuning/recommend``, recommendation list/get/patch
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections.abc import Callable
from typing import Any, TypeVar

from edim_dde_ai import create_agent, list_agents
from edim_dde_ai.observability import build_run_config, get_observability_provider
from edim_dde_ai.recommendations import (
    RecommendationRecord,
    get_recommendation_store,
    new_recommendation_id,
)
from edim_dde_ai.retrieval import get_retrieval_provider, provider_for_corpus
from edim_dde_ai.store import get_state_store
from edim_dde_ai.web import get_web_search_provider
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
from fastapi import APIRouter, Header, HTTPException, Query, Request

from edim_dde_api import __version__
from edim_dde_api.request_context import (
    get_request_id,
    reset_request_id,
    set_request_id,
)
from edim_dde_api.safe_logging import log_exception_once, safe_exc_message
from edim_dde_api.schemas import (
    KnowledgeIngestRequest,
    KnowledgeIngestResponse,
    RcaRequest,
    RcaResponse,
    RecommendationHistoryItem,
    RecommendationStatusUpdate,
    TuningRequest,
    TuningResponse,
    rca_response_from_agent_state,
    tuning_response_from_agent_state,
)

router = APIRouter()
api_v1 = APIRouter(prefix="/api/v1")
logger = logging.getLogger(__name__)

T = TypeVar("T")


def _request_id(
    request: Request,
    x_request_id: str | None,
) -> str:
    """Resolve correlation id from header, request state, or a new UUID.

    Preference order: explicit ``X-Request-Id`` header arg, raw header,
    ``request.state.request_id`` (middleware), then generated UUID.

    Args:
        request: Current FastAPI/Starlette request.
        x_request_id: Value from the ``X-Request-Id`` Header dependency.

    Returns:
        Non-empty request id string.
    """
    existing = getattr(request.state, "request_id", None)
    return (
        x_request_id
        or request.headers.get("x-request-id")
        or (str(existing).strip() if existing else "")
        or ""
    ).strip() or str(uuid.uuid4())


def _http_from_exc(
    *,
    status_code: int,
    exc: BaseException,
    where: str,
    level: int = logging.ERROR,
    detail: str | None = None,
) -> HTTPException:
    """Log original stack once (redacted), then raise a safe HTTPException.

    Args:
        status_code: HTTP status to return to the client.
        exc: Original exception (logged, not necessarily echoed).
        where: Short context string for the log line (route + reason).
        level: Log level (WARNING for expected config / empty-data cases).
        detail: Optional client-facing detail; defaults to redacted exc message.

    Returns:
        ``HTTPException`` ready to ``raise`` (does not raise itself).
    """
    log_exception_once(logger, where, exc, level=level)
    return HTTPException(
        status_code=status_code,
        detail=detail if detail is not None else safe_exc_message(exc),
    )


async def _invoke_agent_in_thread(
    request: Request,
    fn: Callable[[], T],
    *,
    request_id: str | None = None,
) -> T:
    """Run agent work in a worker thread with Apps user token + request id bound.

    Re-binds ``X-Forwarded-Access-Token`` and ``request_id`` inside the thread so
    ContextVars survive BaseHTTPMiddleware / ``asyncio.to_thread`` hops.

    Args:
        request: Incoming request (headers used for forwarded token).
        fn: Synchronous callable that invokes the agent (no args).
        request_id: Optional explicit id; else state / ContextVar.

    Returns:
        Whatever ``fn`` returns (typically final agent state dict).
    """
    token = extract_forwarded_databricks_token(request.headers)
    rid = (
        request_id
        or getattr(request.state, "request_id", None)
        or get_request_id()
        or ""
    ).strip()

    def _run() -> T:
        tok_ctx = set_request_databricks_token(token) if token else None
        rid_ctx = set_request_id(rid) if rid else None
        try:
            return fn()
        finally:
            if rid_ctx is not None:
                reset_request_id(rid_ctx)
            if tok_ctx is not None:
                reset_request_databricks_token(tok_ctx)

    return await asyncio.to_thread(_run)


@router.get("/health")
def health() -> dict[str, Any]:
    """Liveness + plane diagnostics for operators and load balancers.

    HTTP:
        ``GET /health`` → ``200`` JSON with ``status=ok``, registered agent ids,
        package version, and active backend names for observability, state store,
        recommendation store, retrieval, and web search.
    """
    obs = get_observability_provider()
    store = get_state_store()
    retrieval = get_retrieval_provider()
    web_search = get_web_search_provider()
    rec_store = get_recommendation_store()
    return {
        "status": "ok",
        "agents": list_agents(),
        "version": __version__,
        "observability": getattr(obs, "name", "unknown"),
        "state_store": getattr(store, "name", "unknown"),
        "recommendation_store": getattr(rec_store, "name", "unknown"),
        "retrieval": getattr(retrieval, "name", "unknown"),
        "web_search": getattr(web_search, "name", "unknown"),
    }


@api_v1.post("/knowledge/ingest", response_model=KnowledgeIngestResponse)
async def ingest_knowledge(body: KnowledgeIngestRequest) -> KnowledgeIngestResponse:
    """Curated document upsert into the active retrieval backend.

    Requires ``accepted=true`` (Acceptance gate). Platform Jobs remain the
    primary bulk ingest path; this endpoint is for human-approved summaries.

    HTTP:
        ``POST /api/v1/knowledge/ingest`` → ``200`` indexed, ``400`` gate/empty,
        ``501`` backend unsupported, ``503`` upsert failure.

    Args:
        body: Corpus, doc id, text/summary, and acceptance flag.

    Returns:
        ``KnowledgeIngestResponse`` with backend name used for the upsert.
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
        raise _http_from_exc(
            status_code=501,
            exc=exc,
            where="knowledge/ingest not implemented for active retrieval backend",
            level=logging.WARNING,
            detail="Knowledge ingest is not supported for the active retrieval backend",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise _http_from_exc(
            status_code=503,
            exc=exc,
            where="knowledge/ingest failed",
            detail="Knowledge ingest failed; see server logs for details",
        ) from exc

    return KnowledgeIngestResponse(
        status="indexed",
        corpus=body.corpus,
        doc_id=body.doc_id,
        retrieval=getattr(provider, "name", "unknown"),
    )


@api_v1.get("/debug/sql-auth")
def debug_sql_auth(request: Request) -> dict[str, Any]:
    """Non-secret SQL auth diagnostics for Apps bring-up (no token values).

    HTTP:
        ``GET /api/v1/debug/sql-auth`` → ``200`` booleans for Apps runtime and
        whether forwarded / request-scoped tokens are present, plus an operator hint.

    Args:
        request: Used to inspect forwarded-access-token headers.

    Returns:
        Diagnostic dict suitable for Ops troubleshooting (no secrets).
    """
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
    """Run the spark_rca YAML agent end-to-end.

    Invokes ``create_agent("spark_rca")`` in a worker thread, maps ``result`` to
    ``RcaResponse``, then best-effort persists a bounded RecommendationStore row.

    HTTP:
        ``POST /api/v1/rca/analyze`` → ``200`` diagnosis, ``500`` bad agent shape,
        ``502`` domain/SQL tool error, ``503`` Databricks SQL not configured.

    Args:
        body: Job run identity and optional evidence / error text.
        request: For token re-bind and request-id state.
        x_request_id: Optional client correlation header.

    Returns:
        ``RcaResponse``; may include ``recommendation_id`` when store is enabled.
    """
    rid = _request_id(request, x_request_id)
    request.state.request_id = rid
    try:
        agent = create_agent("spark_rca")
        config = build_run_config(agent_id="spark_rca", request_id=rid)
        payload = body.model_dump()
        payload["request_id"] = rid
        final = await _invoke_agent_in_thread(
            request,
            lambda: agent.invoke(payload, config=config),
            request_id=rid,
        )
        response = rca_response_from_agent_state(final)
        return _persist_rca_recommendation(body, response, request_id=rid)
    except ValueError as exc:
        raise _http_from_exc(
            status_code=500,
            exc=exc,
            where="rca/analyze agent result mapping failed",
            detail="RCA agent returned an unexpected result shape",
        ) from exc
    except DatabricksNotConfiguredError as exc:
        raise _http_from_exc(
            status_code=503,
            exc=exc,
            where="rca/analyze Databricks SQL not configured",
            level=logging.WARNING,
            detail=safe_exc_message(exc),
        ) from exc
    except DomainToolError as exc:
        raise _http_from_exc(
            status_code=502,
            exc=exc,
            where="rca/analyze domain/SQL tool failed",
            detail=safe_exc_message(exc),
        ) from exc


@api_v1.post("/cluster_tuning/recommend", response_model=TuningResponse)
async def recommend_cluster(
    body: TuningRequest,
    request: Request,
    x_request_id: str | None = Header(default=None),
) -> TuningResponse:
    """Run the cluster_tuning YAML agent end-to-end.

    Invokes ``create_agent("cluster_tuning")`` in a worker thread, projects agent
    state to ``TuningResponse``, then best-effort persists to RecommendationStore.

    HTTP:
        ``POST /api/v1/cluster_tuning/recommend`` → ``200`` recommendation,
        ``404`` no job metrics, ``502`` domain/SQL tool error,
        ``503`` Databricks SQL not configured.

    Args:
        body: Job/cluster identity, optional date window and metrics override.
        request: For token re-bind and request-id state.
        x_request_id: Optional client correlation header.

    Returns:
        ``TuningResponse``; may include ``recommendation_id`` when store is enabled.
    """
    rid = _request_id(request, x_request_id)
    request.state.request_id = rid
    try:
        agent = create_agent("cluster_tuning")
        config = build_run_config(agent_id="cluster_tuning", request_id=rid)
        payload = body.model_dump()
        payload["request_id"] = rid
        final = await _invoke_agent_in_thread(
            request,
            lambda: agent.invoke(payload, config=config),
            request_id=rid,
        )
        response = tuning_response_from_agent_state(final, request_id=rid)
        response = _attach_tuning_quality(final, response)
        response = _persist_tuning_recommendation(body, response, request_id=rid)
        return response
    except NoJobMetricsError as exc:
        raise _http_from_exc(
            status_code=404,
            exc=exc,
            where="cluster_tuning/recommend no job metrics",
            level=logging.WARNING,
            detail=safe_exc_message(exc),
        ) from exc
    except DatabricksNotConfiguredError as exc:
        raise _http_from_exc(
            status_code=503,
            exc=exc,
            where="cluster_tuning/recommend Databricks SQL not configured",
            level=logging.WARNING,
            detail=safe_exc_message(exc),
        ) from exc
    except DomainToolError as exc:
        raise _http_from_exc(
            status_code=502,
            exc=exc,
            where="cluster_tuning/recommend domain/SQL tool failed",
            detail=safe_exc_message(exc),
        ) from exc


def _bounded_rca_store_response(response: RcaResponse) -> dict[str, Any]:
    """Persist diagnosis fields + a compact evidence snapshot for experience indexing.

    Full evidence packs and regenerated prompt context strings are omitted so
    RecommendationStore rows stay bounded for Cosmos/Redis deployments.

    Keeps:
        root_cause, actions, recommendations, classification_hint, quality,
        and a truncated evidence_pack (anchors + ≤20 excerpts + ≤2k section text).

    Drops:
        runbook_context, historical_context, web_search_context/hits,
        recommendation_id/status (assigned on the outer record).

    Args:
        response: Full HTTP RCA response about to be returned to the client
            (client still receives the full pack; only the **stored** copy is
            compact).

    Returns:
        Dict suitable for ``RecommendationRecord.response``.
    """
    payload = response.model_dump(
        exclude={
            "runbook_context",
            "historical_context",
            "web_search_context",
            "web_search_hits",
            "recommendation_id",
            "recommendation_status",
        }
    )
    pack = response.evidence_pack if isinstance(response.evidence_pack, dict) else {}
    evidence_items: list[dict[str, Any]] = []
    for item in (pack.get("evidence") or [])[:20]:
        if not isinstance(item, dict):
            continue
        evidence_items.append(
            {
                "ref": item.get("ref"),
                "source": item.get("source"),
                "excerpt": str(item.get("excerpt") or "")[:500],
            }
        )
    sections = pack.get("sections") if isinstance(pack.get("sections"), dict) else {}
    compact_sections: dict[str, Any] = {}
    for key, value in sections.items():
        text = str(value or "")
        compact_sections[key] = text[:2000]
    payload["evidence_pack"] = {
        "job_id": pack.get("job_id"),
        "job_run_id": pack.get("job_run_id"),
        "raw_anchors": pack.get("raw_anchors") or {},
        "sections": compact_sections,
        "evidence": evidence_items,
    }
    return payload


def _persist_rca_recommendation(
    body: RcaRequest,
    response: RcaResponse,
    *,
    request_id: str,
) -> RcaResponse:
    """Best-effort save to RecommendationStore; never fail the HTTP success path.

    Writes ``agent_id=spark_rca`` with status ``proposed``. Experience indexing
    for the cross-job corpus waits until status is patched to accepted/applied;
    same-job history can still list proposed rows.

    Args:
        body: Original analyze request (evidence_pack excluded from stored request).
        response: Validated API response to persist (bounded store copy).
        request_id: Correlation id copied onto the lifecycle record.

    Returns:
        Response with ``recommendation_id`` / ``recommendation_status`` set on
        success; unchanged response when store is ``none`` or save fails.
    """
    store = get_recommendation_store()
    if getattr(store, "name", "") == "none":
        return response
    try:
        rec_id = new_recommendation_id()
        record = RecommendationRecord(
            recommendation_id=rec_id,
            agent_id="spark_rca",
            status="proposed",
            job_id=response.job_id or body.job_id,
            job_run_id=response.job_run_id or body.job_run_id,
            request_id=request_id,
            env=os.environ.get("EDIM_ENV"),
            request=body.model_dump(exclude={"evidence_pack"}),
            response=_bounded_rca_store_response(response),
        )
        store.save(record)
        return response.model_copy(
            update={
                "recommendation_id": rec_id,
                "recommendation_status": "proposed",
            }
        )
    except Exception as exc:  # noqa: BLE001
        log_exception_once(
            logger,
            "spark_rca recommendation persist failed",
            exc,
            level=logging.WARNING,
        )
        return response


def _attach_tuning_quality(
    final: dict[str, Any], response: TuningResponse
) -> TuningResponse:
    """Best-effort ``cluster_tuning.quality`` so store rows can be correlated.

    Mirrors RCA's in-graph evaluate: score the recommendation against metrics /
    historical context. Failures are logged and the HTTP success path continues
    without ``quality`` (same as missing quality on older rows).

    Args:
        final: Agent state after invoke (metrics / historical_context).
        response: Projected HTTP response.

    Returns:
        Response with ``quality`` filled when evaluation succeeds.
    """
    if response.quality:
        return response
    try:
        from edim_dde_ai.evaluation import evaluate

        result = evaluate(
            "cluster_tuning.quality",
            inputs={"metrics": final.get("metrics") or response.job_cluster_metrics},
            output={"recommendation": response.recommendation},
            context={
                "historical_context": final.get("historical_context"),
            },
        )
        return response.model_copy(update={"quality": result.to_dict()})
    except Exception as exc:  # noqa: BLE001
        log_exception_once(
            logger,
            "cluster_tuning quality evaluate failed",
            exc,
            level=logging.WARNING,
        )
        return response


def _persist_tuning_recommendation(
    body: TuningRequest,
    response: TuningResponse,
    *,
    request_id: str,
) -> TuningResponse:
    """Best-effort save to RecommendationStore; never fail the HTTP success path.

    Writes ``agent_id=cluster_tuning`` with status ``proposed``. Stores the full
    response dump and request without ``metrics`` (metrics can be large overrides).

    Args:
        body: Original recommend request (``metrics`` excluded from stored request).
        response: Validated API response to persist in full.
        request_id: Correlation id copied onto the lifecycle record.

    Returns:
        Response with ``recommendation_id`` / ``recommendation_status`` set on
        success; unchanged response when store is ``none`` or save fails.
    """
    store = get_recommendation_store()
    if getattr(store, "name", "") == "none":
        return response
    try:
        rec_id = new_recommendation_id()
        record = RecommendationRecord(
            recommendation_id=rec_id,
            agent_id="cluster_tuning",
            status="proposed",
            job_id=response.job_id or body.job_id,
            cluster_id=response.cluster_id or body.cluster_id,
            job_run_id=response.job_run_id or body.job_run_id,
            request_id=request_id,
            env=os.environ.get("EDIM_ENV"),
            request=body.model_dump(exclude={"metrics"}),
            response=response.model_dump(),
        )
        store.save(record)
        return response.model_copy(
            update={
                "recommendation_id": rec_id,
                "recommendation_status": "proposed",
            }
        )
    except Exception as exc:  # noqa: BLE001
        log_exception_once(
            logger,
            "cluster_tuning recommendation persist failed",
            exc,
            level=logging.WARNING,
        )
        return response


def _history_item(record: RecommendationRecord) -> RecommendationHistoryItem:
    """Map a store record to the public history item schema.

    Args:
        record: Persisted recommendation row from RecommendationStore.

    Returns:
        ``RecommendationHistoryItem`` for list/get/patch responses.
    """
    return RecommendationHistoryItem(
        recommendation_id=record.recommendation_id,
        agent_id=record.agent_id,
        status=record.status,
        job_id=record.job_id,
        cluster_id=record.cluster_id,
        job_run_id=record.job_run_id,
        request_id=record.request_id,
        env=record.env,
        created_at=record.created_at,
        updated_at=record.updated_at,
        response=record.response or {},
        request=record.request or {},
    )


def _record_for_agent(
    recommendation_id: str, agent_id: str
) -> RecommendationRecord:
    """Load a recommendation and enforce agent ownership.

    Args:
        recommendation_id: Lifecycle record id from the path.
        agent_id: Expected owning agent (``spark_rca`` or ``cluster_tuning``).

    Returns:
        Matching ``RecommendationRecord``.

    Raises:
        HTTPException: ``404`` when missing or owned by a different agent.
    """
    row = get_recommendation_store().get(recommendation_id)
    if row is None or row.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="recommendation not found")
    return row


@api_v1.get(
    "/rca/recommendations",
    response_model=list[RecommendationHistoryItem],
)
def list_rca_recommendations(
    job_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[RecommendationHistoryItem]:
    """List persisted RCA diagnoses/actions (newest first).

    HTTP:
        ``GET /api/v1/rca/recommendations`` → ``200`` list filtered by optional
        ``job_id`` / ``status``, capped by ``limit`` (1–500).

    Args:
        job_id: Optional job filter.
        status: Optional lifecycle status filter.
        limit: Max rows to return.

    Returns:
        History items for ``agent_id=spark_rca``.
    """
    rows = get_recommendation_store().list(
        job_id=job_id,
        status=status,
        agent_id="spark_rca",
        limit=limit,
    )
    return [_history_item(row) for row in rows]


@api_v1.get(
    "/rca/recommendations/{recommendation_id}",
    response_model=RecommendationHistoryItem,
)
def get_rca_recommendation(recommendation_id: str) -> RecommendationHistoryItem:
    """Fetch one persisted RCA recommendation by id.

    HTTP:
        ``GET /api/v1/rca/recommendations/{recommendation_id}`` → ``200`` item,
        ``404`` if missing or not owned by ``spark_rca``.

    Args:
        recommendation_id: Lifecycle record id.

    Returns:
        Single ``RecommendationHistoryItem``.
    """
    return _history_item(_record_for_agent(recommendation_id, "spark_rca"))


def _apply_status_and_outcome(
    recommendation_id: str,
    body: RecommendationStatusUpdate,
) -> RecommendationRecord:
    """Update lifecycle status and optionally merge outcome scaffolding."""
    store = get_recommendation_store()
    updated = store.update_status(recommendation_id, body.status)
    if updated is None:
        raise HTTPException(status_code=404, detail="recommendation not found")
    if (
        body.human_label is None
        and body.rerun_success is None
        and body.rerun_job_run_id is None
    ):
        return updated
    from edim_dde_domain.evaluation.correlation import merge_outcome_extra

    merged_extra = merge_outcome_extra(
        updated.extra,
        human_label=body.human_label,
        labeled_by=body.labeled_by,
        rerun_success=body.rerun_success,
        rerun_job_run_id=body.rerun_job_run_id,
    )
    updated.extra = merged_extra
    return store.save(updated)


@api_v1.patch(
    "/rca/recommendations/{recommendation_id}",
    response_model=RecommendationHistoryItem,
)
def update_rca_recommendation_status(
    recommendation_id: str,
    body: RecommendationStatusUpdate,
) -> RecommendationHistoryItem:
    """Transition RCA recommendation lifecycle status.

    HTTP:
        ``PATCH /api/v1/rca/recommendations/{recommendation_id}`` → ``200`` updated
        item, ``400`` invalid status transition, ``404`` missing / wrong agent.
        Accepted/applied statuses enable cross-job experience indexing.
        Optional ``human_label`` / ``rerun_success`` fields scaffold Quality 2c
        calibration under ``extra.outcome``.

    Args:
        recommendation_id: Lifecycle record id.
        body: Target ``status`` value (+ optional outcome fields).

    Returns:
        Updated ``RecommendationHistoryItem``.
    """
    _record_for_agent(recommendation_id, "spark_rca")
    try:
        updated = _apply_status_and_outcome(recommendation_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _history_item(updated)


@api_v1.get(
    "/cluster_tuning/recommendations",
    response_model=list[RecommendationHistoryItem],
)
def list_tuning_recommendations(
    job_id: str | None = Query(default=None),
    cluster_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[RecommendationHistoryItem]:
    """List persisted cluster-tuning recommendations (newest first).

    HTTP:
        ``GET /api/v1/cluster_tuning/recommendations`` → ``200`` list filtered by
        optional ``job_id`` / ``cluster_id`` / ``status``, capped by ``limit``.

    Args:
        job_id: Optional job filter.
        cluster_id: Optional cluster filter.
        status: Optional lifecycle status filter.
        limit: Max rows to return (1–500).

    Returns:
        History items for ``agent_id=cluster_tuning``.
    """
    store = get_recommendation_store()
    rows = store.list(
        job_id=job_id,
        cluster_id=cluster_id,
        status=status,
        agent_id="cluster_tuning",
        limit=limit,
    )
    return [_history_item(r) for r in rows]


@api_v1.get(
    "/cluster_tuning/recommendations/{recommendation_id}",
    response_model=RecommendationHistoryItem,
)
def get_tuning_recommendation(recommendation_id: str) -> RecommendationHistoryItem:
    """Fetch one persisted cluster-tuning recommendation by id.

    HTTP:
        ``GET /api/v1/cluster_tuning/recommendations/{recommendation_id}`` →
        ``200`` item, ``404`` if missing or not owned by ``cluster_tuning``.

    Args:
        recommendation_id: Lifecycle record id.

    Returns:
        Single ``RecommendationHistoryItem``.
    """
    return _history_item(_record_for_agent(recommendation_id, "cluster_tuning"))


@api_v1.patch(
    "/cluster_tuning/recommendations/{recommendation_id}",
    response_model=RecommendationHistoryItem,
)
def update_tuning_recommendation_status(
    recommendation_id: str,
    body: RecommendationStatusUpdate,
) -> RecommendationHistoryItem:
    """Transition cluster-tuning recommendation lifecycle status.

    HTTP:
        ``PATCH /api/v1/cluster_tuning/recommendations/{recommendation_id}`` →
        ``200`` updated item, ``400`` invalid transition, ``404`` missing / wrong agent.
        Optional ``human_label`` / ``rerun_success`` scaffold Quality 2c calibration.

    Args:
        recommendation_id: Lifecycle record id.
        body: Target ``status`` value (+ optional outcome fields).

    Returns:
        Updated ``RecommendationHistoryItem``.
    """
    _record_for_agent(recommendation_id, "cluster_tuning")
    try:
        updated = _apply_status_and_outcome(recommendation_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _history_item(updated)
