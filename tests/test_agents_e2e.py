"""API tests: domain bootstrap + invoke with test LLM (no Foundry)."""

from __future__ import annotations

import pytest
from edim_dde_ai import create_agent, set_llm_provider
from edim_dde_ai.registry.agents import clear_agent_cache
from edim_dde_ai.session import clear_checkpointer, configure_checkpointer_from_env
from edim_dde_ai.content.registry import clear_llm_provider
from edim_dde_ai.errors import ConversationMemoryDisabledError
from edim_dde_domain import bootstrap_agents, reset_bootstrap
from edim_dde_domain.sources import clear_sources
from edim_dde_domain.testing import DomainStubLLM
from edim_dde_ai.session.host import normalize_conversation_payload
from edim_dde_api.schemas import TuningRequest
from fastapi.testclient import TestClient


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


@pytest.fixture
def client(_agents_with_stub_llm):
    # Import after agents are registered. Lifespan may replace the LLM provider
    # with LazyFoundry — restore the stub for offline HTTP tests.
    from edim_dde_api.main import app

    with TestClient(app) as test_client:
        set_llm_provider(DomainStubLLM())
        yield test_client


def test_spark_rca_with_evidence_override():
    agent = create_agent("spark_rca")
    out = agent.invoke(
        {
            "skip_hitl": True,
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
            "skip_hitl": True,
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
    assert "resource_optimization_pct" in out["recommendation"]
    assert "cost" not in (out.get("comparison") or {})


def test_health_http(client: TestClient):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "cluster_tuning" in body["agents"]
    assert "spark_rca" in body["agents"]
    assert body["web_search"] in {"none", "memory", "http_json"}


def test_disabled_memory_rejects_conversation_id():
    body = TuningRequest(
        job_id="j-disabled",
        cluster_id="c-1",
        conversation_id="existing-conversation",
        message="Can we reduce the worker count further?",
    )

    with pytest.raises(ConversationMemoryDisabledError) as exc_info:
        normalize_conversation_payload(
            body,
            request_id="r-disabled",
            memory_enabled=False,
        )

    assert "memory is disabled" in str(exc_info.value)


def test_disabled_memory_http_rejects_conversation_id(client: TestClient):
    res = client.post(
        "/api/v1/sessions",
        json={
            "agent_id": "hitl_demo",
            "state": {"conversation_id": "existing-conversation", "name": "alpha"},
        },
    )

    assert res.status_code == 422
    assert res.json()["error_code"] == "CONVERSATION_MEMORY_DISABLED"


def test_disabled_memory_treats_message_as_standalone():
    body = TuningRequest(
        job_id="j-standalone",
        cluster_id="c-1",
        message="Explain this recommendation.",
    )

    payload, conversation_id = normalize_conversation_payload(
        body,
        request_id="r-standalone",
        memory_enabled=False,
    )

    assert conversation_id is None
    assert "conversation_id" not in payload
    assert payload["user_message"] == "Explain this recommendation."


def test_cluster_tuning_recommend_v1_http(client: TestClient):
    res = client.post(
        "/api/v1/cluster_tuning/recommend",
        json={
            "skip_hitl": True,
            "job_id": "j-1",
            "cluster_id": "c-1",
            "include_explanation": False,
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
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["job_id"] == "j-1"
    assert body["recommendation"]["recommended_max_workers"] < 16
    assert "resource_optimization" in body["comparison"]
    assert "cost" not in body["comparison"]
    assert body.get("recommendation_id")
    assert body.get("recommendation_status") == "proposed"
    rid = body["recommendation_id"]
    listed = client.get(
        "/api/v1/cluster_tuning/recommendations", params={"job_id": "j-1"}
    )
    assert listed.status_code == 200
    assert any(row["recommendation_id"] == rid for row in listed.json())
    got = client.get(f"/api/v1/cluster_tuning/recommendations/{rid}")
    assert got.status_code == 200
    assert got.json()["job_id"] == "j-1"
    patched = client.patch(
        f"/api/v1/cluster_tuning/recommendations/{rid}",
        json={"status": "accepted"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "accepted"
    # Unversioned path removed
    assert client.post(
        "/api/v1/recommendations", json={"job_id": "j", "cluster_id": "c"}
    ).status_code == 404


def test_cluster_tuning_conversation_follow_up(client: TestClient):
    clear_agent_cache()
    clear_checkpointer()
    configure_checkpointer_from_env()
    first = client.post(
        "/api/v1/cluster_tuning/recommend",
        json={
            "skip_hitl": True,
            "job_id": "j-conversation",
            "cluster_id": "c-1",
            "message": "Explain the recommendation for the engineer review.",
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
        },
    )
    assert first.status_code == 200
    conversation_id = first.json()["conversation_id"]
    follow_up = client.post(
        "/api/v1/cluster_tuning/recommend",
        json={
            "skip_hitl": True,
            "job_id": "j-conversation",
            "cluster_id": "c-1",
            "conversation_id": conversation_id,
            "message": "Can we reduce the worker count further?",
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
        },
    )
    assert follow_up.status_code == 200
    assert follow_up.json()["conversation_id"] == conversation_id


def test_health_includes_recommendation_store(client: TestClient):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert "recommendation_store" in body
    assert body["recommendation_store"] in {"memory", "none", "postgres", "cosmos", "redis"}


def test_rca_analyze_v1_http(client: TestClient):
    res = client.post(
        "/api/v1/rca/analyze",
        json={
            "skip_hitl": True,
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
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"
    assert body["root_cause"]["category"] == "resource"
    assert "recommended_actions" in body
    assert body["quality"]["evaluator"] == "spark_rca.quality"
    assert body["recommendation_status"] == "proposed"
    rid = body["recommendation_id"]
    assert rid
    listed = client.get(
        "/api/v1/rca/recommendations", params={"job_id": "j-1"}
    )
    assert listed.status_code == 200
    assert any(row["recommendation_id"] == rid for row in listed.json())
    got = client.get(f"/api/v1/rca/recommendations/{rid}")
    assert got.status_code == 200
    assert got.json()["agent_id"] == "spark_rca"
    stored = got.json()["response"]
    assert "runbook_context" not in stored
    assert "historical_context" not in stored
    assert "web_search_hits" not in stored
    pack = stored["evidence_pack"]
    assert pack["raw_anchors"]["failure_reason"]
    assert pack["evidence"][0]["ref"] == "e1"
    patched = client.patch(
        f"/api/v1/rca/recommendations/{rid}",
        json={"status": "applied"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "applied"
    # Agent-scoped routes cannot read a different agent's lifecycle record.
    assert (
        client.get(f"/api/v1/cluster_tuning/recommendations/{rid}").status_code
        == 404
    )
    # Must not leak full agent state keys
    assert "sizing_raw" not in body
    assert "llm_raw" not in body


def test_hitl_session_pause_get_resume(client: TestClient):
    started = client.post(
        "/api/v1/sessions",
        json={"agent_id": "hitl_demo", "state": {"name": "alpha"}},
        headers={"X-Request-Id": "hitl-test-001"},
    )
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["status"] == "waiting_hitl"
    assert body["session_id"]
    assert body["state"]["proposal"] == "resize-alpha"
    sid = body["session_id"]

    got = client.get(f"/api/v1/sessions/{sid}")
    assert got.status_code == 200
    assert got.json()["status"] == "waiting_hitl"

    resumed = client.post(
        f"/api/v1/sessions/{sid}/resume",
        json={"decision": "approved", "comment": "ok"},
        headers={"X-Request-Id": "hitl-test-001"},
    )
    assert resumed.status_code == 200, resumed.text
    out = resumed.json()
    assert out["status"] == "closed"
    assert out["state"]["status"] == "done:approved"
    assert out["state"]["proposal"] == "resize-alpha"

    again = client.post(
        f"/api/v1/sessions/{sid}/resume",
        json={"decision": "approved"},
    )
    assert again.status_code == 409


_METRICS = {
    "azure_worker_vm_size": "Standard_E8s_v3",
    "max_worker_nodes_provisioned": 16,
    "avg_worker_nodes_consumed": 4.0,
    "p99_worker_nodes_consumed": 5.0,
    "peak_worker_cpu_utilization_pct": 20,
    "peak_worker_memory_utilization_pct": 25,
    "avg_worker_cpu_utilization_pct": 15,
    "avg_worker_memory_utilization_pct": 18,
    "driver_node_count": 1,
}


def test_cluster_tuning_hitl_approve_modify(client: TestClient):
    paused = client.post(
        "/api/v1/cluster_tuning/recommend",
        json={
            "job_id": "j-hitl-tune",
            "cluster_id": "c-1",
            "include_explanation": False,
            "metrics": _METRICS,
        },
    )
    assert paused.status_code == 200, paused.text
    body = paused.json()
    assert body["status"] == "waiting_hitl"
    assert body.get("session_id")
    assert body.get("recommendation")
    assert not body.get("recommendation_id")
    sid = body["session_id"]

    bad = client.post(
        f"/api/v1/sessions/{sid}/resume",
        json={"decision": "modified", "patch": {"not_allowed": 1}},
    )
    assert bad.status_code == 400

    resumed = client.post(
        f"/api/v1/sessions/{sid}/resume",
        json={
            "decision": "modified",
            "comment": "lower workers",
            "patch": {"recommended_max_workers": 3},
        },
    )
    assert resumed.status_code == 200, resumed.text
    out = resumed.json()
    assert out["status"] == "closed"
    assert out["state"]["recommendation"]["recommended_max_workers"] == 3
    assert out["state"].get("recommendation_id")


def test_spark_rca_hitl_approve_only(client: TestClient):
    paused = client.post(
        "/api/v1/rca/analyze",
        json={
            "job_run_id": "jr-hitl-1",
            "job_id": "j-hitl-rca",
            "evidence_pack": {
                "job_run_id": "jr-hitl-1",
                "evidence": [
                    {"ref": "e1", "excerpt": "Executor OutOfMemoryError: Java heap space"}
                ],
                "raw_anchors": {
                    "failure_reason": "Executor OutOfMemoryError: Java heap space"
                },
            },
        },
    )
    assert paused.status_code == 200, paused.text
    body = paused.json()
    assert body["status"] == "waiting_hitl"
    assert body.get("session_id")
    assert body.get("root_cause")
    assert not body.get("recommendation_id")
    sid = body["session_id"]

    denied = client.post(
        f"/api/v1/sessions/{sid}/resume",
        json={"decision": "modified", "patch": {"root_cause": {}}},
    )
    assert denied.status_code == 400

    resumed = client.post(
        f"/api/v1/sessions/{sid}/resume",
        json={"decision": "approved", "comment": "looks good"},
    )
    assert resumed.status_code == 200, resumed.text
    out = resumed.json()
    assert out["status"] == "closed"
    assert out["state"].get("hitl_outcome") == "approved"
    assert out["state"].get("recommendation_id")
