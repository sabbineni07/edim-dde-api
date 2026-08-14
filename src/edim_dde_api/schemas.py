"""Pydantic request/response models (OpenAPI contract for /api/v1)."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class RcaRequest(BaseModel):
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


class RootCause(BaseModel):
    category: str
    summary: str
    confidence: float
    confidence_label: Optional[str] = None
    failure_signature: Optional[str] = None


class RcaResponse(BaseModel):
    """Stable HTTP shape for Spark RCA (not the full agent state bag)."""

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
    recommendations: dict[str, Any] = Field(default_factory=dict)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    classification_hint: dict[str, Any] = Field(default_factory=dict)
    evidence_pack: Optional[dict[str, Any]] = None


class KnowledgeIngestRequest(BaseModel):
    """Curated knowledge upsert (Acceptance-gated). Bulk ingest stays in Jobs."""

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
    status: str
    corpus: str
    doc_id: str
    retrieval: str


class TuningRequest(BaseModel):
    job_id: str = Field(..., examples=["job-42"])
    cluster_id: str = Field(..., examples=["cluster-abc"])
    job_run_id: Optional[str] = None
    start_date: Optional[str] = Field(
        None, description="Optional lower bound on job_run_date (YYYY-MM-DD)"
    )
    end_date: Optional[str] = Field(
        None, description="Optional upper bound on job_run_date (YYYY-MM-DD)"
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


class TuningResponse(BaseModel):
    """Stable HTTP shape for cluster tuning (projected from agent state)."""

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


def rca_response_from_agent_state(final: dict[str, Any]) -> RcaResponse:
    """Map agent state → RcaResponse; require ``result`` (no full-state fallback)."""
    result = final.get("result")
    if not isinstance(result, dict):
        raise ValueError("spark_rca agent state missing result object")
    return RcaResponse.model_validate(result)


def tuning_response_from_agent_state(
    final: dict[str, Any], *, request_id: str | None = None
) -> TuningResponse:
    """Map agent state → TuningResponse (explicit field projection)."""
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
    )
