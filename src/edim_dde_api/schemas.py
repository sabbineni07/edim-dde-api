"""Pydantic request/response models."""

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
        description="Used only in stub mode when Databricks is not configured",
        examples=["Executor OutOfMemoryError: Java heap space"],
    )
    evidence_pack: Optional[dict[str, Any]] = None


class TuningRequest(BaseModel):
    job_id: str = Field(..., examples=["job-42"])
    cluster_id: str = Field(..., examples=["cluster-abc"])
    job_run_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    include_explanation: bool = False
    metrics: Optional[dict[str, Any]] = Field(
        None,
        description="Optional override; otherwise tools query Databricks SQL",
        examples=[
            {
                "azure_worker_vm_size": "Standard_E8s_v3",
                "max_worker_nodes_provisioned": 16,
                "peak_worker_cpu_utilization_pct": 25,
                "peak_worker_memory_utilization_pct": 30,
            }
        ],
    )
