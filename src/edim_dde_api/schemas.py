"""Pydantic request/response models (OpenAPI contract for /api/v1).

Business purpose
----------------
Stable HTTP shapes for Spark RCA, cluster tuning, curated knowledge ingest,
and recommendation lifecycle. Route handlers map agent state into these models
so clients never depend on the full LangGraph state bag.

Public API / endpoint groups
----------------------------
* RCA — ``RcaRequest``, ``RootCause``, ``RcaResponse``, ``rca_response_from_agent_state``
* Cluster tuning — ``TuningRequest``, ``TuningResponse``, ``tuning_response_from_agent_state``
* Knowledge — ``KnowledgeIngestRequest``, ``KnowledgeIngestResponse``
* Recommendation history — ``RecommendationStatusUpdate``, ``RecommendationHistoryItem``
* HITL sessions — ``SessionStartRequest``, ``HitlResumeRequest``, ``SessionResponse``
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class RcaRequest(BaseModel):
    """POST ``/api/v1/rca/analyze`` body — identify a failed Spark job run.

    Attributes:
        job_run_id: Required Databricks job run id to diagnose.
        job_id: Optional parent job id (improves history / experience lookup).
        job_run_date: Optional run date (YYYY-MM-DD) for SQL windowing.
        task_key: Optional multi-task job task key when diagnosing one task.
        workspace_id: Optional within-env workspace for warehouse/UC FQNs
            (must belong to process ``EDIM_ENV``; never cross-env).
        error_text: Optional failure text for classification with evidence.
        evidence_pack: Optional pre-built evidence; otherwise agent gathers via SQL.
        conversation_id: Optional conversation key for follow-up questions when
            memory is enabled.
        message: Optional engineer question; standalone when memory is disabled.
    """

    job_run_id: str = Field(..., examples=["jr-1001"])
    job_id: Optional[str] = Field(None, examples=["job-42"])
    job_run_date: Optional[str] = Field(None, examples=["2026-07-18"])
    task_key: Optional[str] = None
    workspace_id: Optional[str] = None
    error_text: Optional[str] = Field(
        None,
        description="Optional failure text for classification when provided with evidence",
        examples=["Executor OutOfMemoryError: Java heap space"],
    )
    evidence_pack: Optional[dict[str, Any]] = None
    conversation_id: Optional[str] = Field(
        None,
        max_length=200,
        description="Conversation key returned by a prior RCA response when memory is enabled",
    )
    message: Optional[str] = Field(
        None,
        max_length=8000,
        description="Optional engineer question; standalone when memory is disabled",
    )


class RootCause(BaseModel):
    """Diagnosed root cause embedded in ``RcaResponse``.

    Attributes:
        category: Failure taxonomy bucket (e.g. memory, skew, config).
        summary: Human-readable one-line diagnosis.
        confidence: Rubric / pipeline confidence in ``[0, 1]``.
        model_confidence: LLM/rule estimate; prefer ``quality.confidence`` for
            evidence-completeness rubric.
        confidence_label: Optional qualitative label (high/medium/low).
        failure_signature: Optional normalized signature for experience matching.
    """

    category: str
    summary: str
    confidence: float
    model_confidence: Optional[float] = Field(
        None, description="LLM/rule estimate; use response.quality.confidence for rubric evidence completeness"
    )
    confidence_label: Optional[str] = None
    failure_signature: Optional[str] = None


class RcaResponse(BaseModel):
    """Stable HTTP shape for Spark RCA (not the full agent state bag).

    Attributes:
        request_id: Correlation id echoed from the request / middleware.
        job_id / job_run_id / task_key: Job identity resolved by the agent.
        status: Pipeline status (default ``completed``).
        job_status: Databricks job/run status when known.
        root_cause: Structured diagnosis (required).
        recommended_actions: Ordered remediation steps.
        contributing_factors: Secondary factors supporting the diagnosis.
        evidence_analysis: Structured analysis over gathered evidence.
        possible_causes: Ranked alternative hypotheses.
        context_assessment: Runbook / history / web context summary.
        recommendations: Structured recommendation payload for operators.
        timeline: Chronological events from the run.
        evidence: Evidence items surfaced to the client. Each item carries a
            ``backfilled`` flag; when the model cited nothing resolvable these
            are labeled pack-preview rows, not model citations.
        evidence_backfilled: True when ``evidence`` holds pack preview rows the
            model did not cite (never a silent substitution).
        classification_hint: Early classification signals from the graph.
        evidence_pack: Full or gathered evidence pack (client receives full).
        runbook_context / historical_context / web_search_*: Enrichment strings
            and hits (omitted from bounded store persistence).
        quality: Rubric / QA scores from the agent.
        recommendation_id / recommendation_status: Lifecycle fields when
            RecommendationStore persist succeeds.
        explanation: Optional narrative from session converse follow-ups.
        conversation_id: Session key for multi-turn follow-ups.
    """

    request_id: Optional[str] = None
    job_id: Optional[str] = None
    job_run_id: Optional[str] = None
    task_key: Optional[str] = None
    status: str = "completed"
    job_status: Optional[str] = None
    root_cause: RootCause
    recommended_actions: list[str] = Field(default_factory=list)
    contributing_factors: list[str] = Field(default_factory=list)
    evidence_analysis: dict[str, Any] = Field(default_factory=dict)
    possible_causes: list[dict[str, Any]] = Field(default_factory=list)
    context_assessment: dict[str, Any] = Field(default_factory=dict)
    recommendations: dict[str, Any] = Field(default_factory=dict)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    evidence_backfilled: bool = Field(
        False,
        description=(
            "True when `evidence` holds labeled pack-preview rows the model did "
            "not cite (never a silent citation substitution)."
        ),
    )
    classification_hint: dict[str, Any] = Field(default_factory=dict)
    evidence_pack: Optional[dict[str, Any]] = None
    runbook_context: Optional[str] = None
    historical_context: Optional[str] = None
    web_search_context: Optional[str] = None
    web_search_hits: list[dict[str, Any]] = Field(default_factory=list)
    quality: dict[str, Any] = Field(default_factory=dict)
    explanation: str = Field(
        "",
        description="Optional narrative from session converse follow-ups",
    )
    conversation_id: Optional[str] = None
    recommendation_id: Optional[str] = Field(
        None, description="Persisted RCA lifecycle record id when enabled"
    )
    recommendation_status: Optional[str] = Field(
        None, description="Lifecycle status when persisted (initially proposed)"
    )


class KnowledgeIngestRequest(BaseModel):
    """Curated knowledge upsert (Acceptance-gated). Bulk ingest stays in Jobs.

    Attributes:
        corpus: Target retrieval corpus name (e.g. ``spark-runbooks``).
        doc_id: Stable document id for upsert / overwrite.
        text: Full document or chunk body to index.
        summary: Optional user summary prepended to ``text`` for retrieval.
        accepted: Must be ``true`` — Acceptance gate before indexing.
        source: Optional provenance string (URL, wiki path, author).
        metadata: Opaque key/value bag stored with the document.
    """

    corpus: str = Field(..., examples=["spark-runbooks"])
    doc_id: str = Field(..., examples=["oom-playbook-v2"])
    text: str = Field(
        "",
        description="Full document/chunk body to index",
    )
    summary: Optional[str] = Field(
        None,
        description="User-provided summary prepended to text for better retrieval",
    )
    accepted: bool = Field(
        False,
        description="Must be true — Acceptance gate before indexing",
    )
    source: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeIngestResponse(BaseModel):
    """POST ``/api/v1/knowledge/ingest`` result.

    Attributes:
        status: Outcome label (e.g. ``indexed``).
        corpus: Corpus that received the upsert.
        doc_id: Document id that was indexed.
        retrieval: Active retrieval backend name (for operator diagnostics).
    """

    status: str
    corpus: str
    doc_id: str
    retrieval: str


class TuningRequest(BaseModel):
    """POST ``/api/v1/cluster_tuning/recommend`` body — size a job cluster.

    Attributes:
        job_id: Databricks job whose cluster should be tuned.
        cluster_id: Current / target cluster id for metrics and comparison.
        job_run_id: Optional specific run to anchor the recommendation.
        start_date / end_date: Optional ``job_run_date`` bounds (YYYY-MM-DD).
        workspace_id: Optional within-env workspace for warehouse/UC FQNs
            (must belong to process ``EDIM_ENV``; see workspace resolver).
        include_explanation: When true, agent may populate ``explanation``.
        metrics: Optional metrics override; otherwise domain SQL reads Databricks.
        conversation_id: Optional conversation key returned by a prior response
            when memory is enabled.
        message: Optional engineer question; standalone when memory is disabled.
    """

    job_id: str = Field(..., examples=["job-42"])
    cluster_id: str = Field(..., examples=["cluster-abc"])
    job_run_id: Optional[str] = None
    start_date: Optional[str] = Field(
        None, description="Optional lower bound on job_run_date (YYYY-MM-DD)"
    )
    end_date: Optional[str] = Field(
        None, description="Optional upper bound on job_run_date (YYYY-MM-DD)"
    )
    workspace_id: Optional[str] = Field(
        None,
        description=(
            "Within-env Databricks workspace id (e.g. dev_1). "
            "Never resolves across EDIM_ENV boundaries."
        ),
        examples=["dev_1"],
    )
    include_explanation: bool = False
    metrics: Optional[dict[str, Any]] = Field(
        None,
        description="Optional override; otherwise domain.sql.query reads Databricks",
        examples=[
            {
                "azure_worker_vm_size": "Standard_E8s_v3",
                "max_worker_nodes_provisioned": 16,
                "avg_worker_nodes_consumed": 4.0,
                "peak_worker_cpu_utilization_pct": 25,
                "peak_worker_memory_utilization_pct": 30,
                "avg_worker_cpu_utilization_pct": 20,
                "avg_worker_memory_utilization_pct": 22,
            }
        ],
    )
    conversation_id: Optional[str] = Field(
        None,
        max_length=200,
        description="Conversation key returned by a prior tuning response when memory is enabled",
    )
    message: Optional[str] = Field(
        None,
        max_length=8000,
        description="Optional engineer question; standalone when memory is disabled",
    )


class TuningResponse(BaseModel):
    """Stable HTTP shape for cluster tuning (projected from agent state).

    Attributes:
        request_id: Correlation id for the recommend call.
        job_id / cluster_id / job_run_id: Identity echoed / resolved by the agent.
        recommendation: Proposed SKU / node / config changes.
        current_configuration: Snapshot of the current cluster config.
        comparison: Diff / delta between current and recommended.
        risk_assessment: Risk notes and severity for applying the change.
        performance_validation: Guardrail / performance checks from the graph.
        pattern_analysis: Narrative pattern summary over historical metrics.
        reason_codes: Machine-readable reasons for the recommendation.
        guardrail_adjustments: Adjustments applied when guardrails fired.
        sizing_attempts: How many sizing iterations the graph ran.
        guardrail_retries: Guardrail retry count (defaults from attempts).
        job_cluster_metrics: Metrics bag used (or fetched) for sizing.
        explanation: Optional human narrative when requested.
        recommendation_id / recommendation_status: Lifecycle fields when
            RecommendationStore persist succeeds.
        quality: Deterministic ``cluster_tuning.quality`` rubric snapshot
            (score / confidence / dimensions) when evaluation succeeds.
        conversation_id: Conversation key for follow-up questions.
    """

    request_id: Optional[str] = None
    job_id: Optional[str] = None
    cluster_id: Optional[str] = None
    job_run_id: Optional[str] = None
    recommendation: dict[str, Any] = Field(default_factory=dict)
    current_configuration: dict[str, Any] = Field(default_factory=dict)
    comparison: dict[str, Any] = Field(default_factory=dict)
    risk_assessment: dict[str, Any] = Field(default_factory=dict)
    performance_validation: dict[str, Any] = Field(default_factory=dict)
    pattern_analysis: str = ""
    reason_codes: list[str] = Field(default_factory=list)
    guardrail_adjustments: list[Any] = Field(default_factory=list)
    sizing_attempts: int = 1
    guardrail_retries: int = 0
    job_cluster_metrics: dict[str, Any] = Field(default_factory=dict)
    explanation: str = ""
    recommendation_id: Optional[str] = Field(
        None,
        description="Persisted history id when recommendation store is enabled",
    )
    recommendation_status: Optional[str] = Field(
        None,
        description="Lifecycle status when persisted (e.g. proposed)",
    )
    quality: dict[str, Any] = Field(
        default_factory=dict,
        description="cluster_tuning.quality rubric snapshot when evaluated",
    )
    conversation_id: Optional[str] = None


class RecommendationStatusUpdate(BaseModel):
    """PATCH body for recommendation lifecycle transitions.

    Attributes:
        status: Target status — ``proposed`` | ``accepted`` | ``rejected`` |
            ``applied`` | ``superseded``.
        human_label: Optional calibration label stored under ``extra.outcome``.
        labeled_by: Optional actor for the human label.
        rerun_success: Optional post-change success flag (Quality 2c scaffold).
        rerun_job_run_id: Optional follow-up run id for the rerun measurement.
    """

    status: str = Field(
        ...,
        description="proposed | accepted | rejected | applied | superseded",
        examples=["accepted"],
    )
    human_label: Optional[str] = Field(
        None,
        description="Optional human calibration label (stored in extra.outcome)",
    )
    labeled_by: Optional[str] = Field(
        None,
        description="Optional actor for human_label",
    )
    rerun_success: Optional[bool] = Field(
        None,
        description="Optional post-apply / rerun success flag",
    )
    rerun_job_run_id: Optional[str] = Field(
        None,
        description="Optional job_run_id for the measured rerun",
    )


class RecommendationHistoryItem(BaseModel):
    """One row from RecommendationStore list/get endpoints.

    Attributes:
        recommendation_id: Stable lifecycle record id.
        agent_id: Owning agent (``spark_rca`` or ``cluster_tuning``).
        status: Current lifecycle status.
        job_id / cluster_id / job_run_id: Optional identity filters / display.
        request_id: Correlation id from the original analyze/recommend call.
        env: Deployment env tag (from ``EDIM_ENV`` at persist time).
        created_at / updated_at: ISO timestamps when the store provides them.
        response: Stored response payload (bounded for RCA).
        request: Stored request payload (large fields like evidence/metrics excluded).
    """

    recommendation_id: str
    agent_id: str = "cluster_tuning"
    status: str
    job_id: Optional[str] = None
    cluster_id: Optional[str] = None
    job_run_id: Optional[str] = None
    request_id: Optional[str] = None
    env: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    response: dict[str, Any] = Field(default_factory=dict)
    request: dict[str, Any] = Field(default_factory=dict)


def rca_response_from_agent_state(final: dict[str, Any]) -> RcaResponse:
    """Map agent state → RcaResponse; require ``result`` (no full-state fallback).

    Args:
        final: Final ``spark_rca`` agent state after ``invoke``.

    Returns:
        Validated ``RcaResponse`` from ``final["result"]``, plus optional
        session ``explanation`` / ``conversation_id`` from the outer state.

    Raises:
        ValueError: When ``result`` is missing or not a dict.
    """
    result = final.get("result")
    if not isinstance(result, dict):
        raise ValueError("spark_rca agent state missing result object")
    payload = dict(result)
    explanation = str(final.get("explanation") or payload.get("explanation") or "")
    if explanation:
        payload["explanation"] = explanation
    conversation_id = final.get("conversation_id") or final.get("thread_id")
    if conversation_id:
        payload["conversation_id"] = conversation_id
    return RcaResponse.model_validate(payload)


def tuning_response_from_agent_state(
    final: dict[str, Any], *, request_id: str | None = None
) -> TuningResponse:
    """Map agent state → TuningResponse (explicit field projection).

    Derives ``guardrail_retries`` from ``sizing_attempts`` when the agent omits it.

    Args:
        final: Final ``cluster_tuning`` agent state after ``invoke``.
        request_id: Optional override when the HTTP layer owns the correlation id.

    Returns:
        Projected ``TuningResponse`` (empty dicts/lists for missing fields).
    """
    attempts = int(final.get("sizing_attempts") or 1)
    retries = final.get("guardrail_retries")
    if retries is None:
        retries = max(0, attempts - 1)
    return TuningResponse(
        request_id=request_id or final.get("request_id"),
        job_id=final.get("job_id"),
        cluster_id=final.get("cluster_id"),
        job_run_id=final.get("job_run_id"),
        recommendation=final.get("recommendation") or {},
        current_configuration=final.get("current_configuration") or {},
        comparison=final.get("comparison") or {},
        risk_assessment=final.get("risk_assessment") or {},
        performance_validation=final.get("performance_validation") or {},
        pattern_analysis=str(final.get("pattern_analysis") or ""),
        reason_codes=list(final.get("reason_codes") or []),
        guardrail_adjustments=list(final.get("guardrail_adjustments") or []),
        sizing_attempts=attempts,
        guardrail_retries=int(retries),
        job_cluster_metrics=final.get("metrics") or {},
        explanation=str(final.get("explanation") or ""),
        recommendation_id=final.get("recommendation_id"),
        recommendation_status=final.get("recommendation_status"),
        quality=dict(final.get("quality") or {}),
    )


class SessionStartRequest(BaseModel):
    """POST ``/api/v1/sessions`` — start an agent run that may pause at HITL."""

    agent_id: str = Field(..., examples=["hitl_demo"])
    state: dict[str, Any] = Field(default_factory=dict)


class HitlResumeRequest(BaseModel):
    """POST ``/api/v1/sessions/{session_id}/resume`` body."""

    decision: str = Field(
        ...,
        description="approved | rejected | modified",
        examples=["approved"],
    )
    comment: Optional[str] = None
    patch: Optional[dict[str, Any]] = Field(
        None,
        description="Optional state keys to merge (typical for modified)",
    )
    actor: Optional[str] = None


class SessionResponse(BaseModel):
    """HITL / session snapshot returned by start, get, and resume."""

    session_id: Optional[str] = None
    agent_id: str
    status: str
    hitl_prompt: Optional[str] = None
    hitl_gate_id: Optional[str] = None
    hitl_decision: Optional[str] = None
    request_id: Optional[str] = None
    state: dict[str, Any] = Field(default_factory=dict)
