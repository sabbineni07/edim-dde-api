"""API tests: domain bootstrap + invoke with test LLM (no Foundry)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from edim_dde_ai import create_agent, set_llm_provider
from edim_dde_ai.content.registry import clear_llm_provider
from edim_dde_domain import bootstrap_agents, reset_bootstrap
from edim_dde_domain.sources import clear_sources

# Reuse domain test stub (mocks stay in tests/, not production packages).
_DOMAIN_TESTS = Path(__file__).resolve().parents[2] / "edim-dde-domain" / "tests"
if _DOMAIN_TESTS.is_dir() and str(_DOMAIN_TESTS) not in sys.path:
    sys.path.insert(0, str(_DOMAIN_TESTS))

from llm_stub import DomainStubLLM  # noqa: E402


@pytest.fixture(autouse=True)
def _agents_with_stub_llm():
    clear_sources()
    reset_bootstrap()
    set_llm_provider(DomainStubLLM())
    bootstrap_agents()
    yield
    reset_bootstrap()
    clear_llm_provider()
    clear_sources()


def test_spark_rca_with_evidence_override():
    agent = create_agent("spark_rca")
    out = agent.invoke(
        {
            "job_run_id": "jr-1",
            "job_id": "j-1",
            "evidence_pack": {
                "job_run_id": "jr-1",
                "evidence": [
                    {
                        "ref": "e1",
                        "excerpt": "Executor OutOfMemoryError: Java heap space",
                    }
                ],
                "raw_anchors": {
                    "failure_reason": "Executor OutOfMemoryError: Java heap space"
                },
            },
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
                "avg_worker_nodes_consumed": 4.0,
                "p99_worker_nodes_consumed": 5.0,
                "peak_worker_cpu_utilization_pct": 20,
                "peak_worker_memory_utilization_pct": 25,
                "avg_worker_cpu_utilization_pct": 15,
                "avg_worker_memory_utilization_pct": 18,
                "driver_node_count": 1,
            },
        }
    )
    assert out["recommendation"]["recommended_max_workers"] < 16
    assert out["explanation"]
