"""API tests: domain bootstrap + invoke (no local agent copies)."""

from __future__ import annotations

from edim_dde_ai import create_agent
from edim_dde_domain import bootstrap_agents


def setup_module() -> None:
    bootstrap_agents()


def test_spark_rca_oom():
    agent = create_agent("spark_rca")
    out = agent.invoke(
        {
            "job_run_id": "jr-1",
            "job_id": "j-1",
            "error_text": "Executor OutOfMemoryError: Java heap space",
        }
    )
    assert out["result"]["root_cause"]["category"] == "resource"


def test_cluster_tuning_with_explanation():
    agent = create_agent("cluster_tuning")
    out = agent.invoke(
        {
            "job_id": "j-1",
            "cluster_id": "c-1",
            "include_explanation": True,
            "metrics": {
                "azure_worker_vm_size": "Standard_E8s_v3",
                "max_worker_nodes_provisioned": 16,
                "peak_worker_cpu_utilization_pct": 20,
                "peak_worker_memory_utilization_pct": 25,
            },
        }
    )
    assert out["recommendation"]["recommended_max_workers"] < 16
    assert out["explanation"]
