"""Agent Directory Phase 2 stubs (ADR-001)."""

from __future__ import annotations

import json

import pytest
from edim_dde_ai import set_llm_provider
from edim_dde_ai.a2a.bindings import clear_runtime_bindings
from edim_dde_ai.content.registry import clear_llm_provider
from edim_dde_domain import bootstrap_agents, reset_bootstrap
from edim_dde_domain.sources import clear_sources
from edim_dde_domain.testing import DomainStubLLM
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _agents_with_stub_llm():
    clear_sources()
    reset_bootstrap()
    clear_runtime_bindings()
    set_llm_provider(DomainStubLLM())
    bootstrap_agents()
    yield
    reset_bootstrap()
    clear_llm_provider()
    clear_sources()
    clear_runtime_bindings()


@pytest.fixture
def client(_agents_with_stub_llm):
    from edim_dde_api.main import app

    with TestClient(app) as test_client:
        set_llm_provider(DomainStubLLM())
        yield test_client


def test_directory_health(client: TestClient):
    res = client.get("/api/v1/directory/health")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "ok"
    assert body["agent_count"] >= 3
    assert body["source"] == "in_process_registry"
    assert body["env"]


def test_directory_list_and_get(client: TestClient):
    listed = client.get("/api/v1/directory/agents")
    assert listed.status_code == 200, listed.text
    payload = listed.json()
    ids = {a["agent_id"] for a in payload["agents"]}
    assert "cluster_tuning" in ids
    assert "spark_rca" in ids
    assert "hitl_demo" in ids
    for agent in payload["agents"]:
        if agent["agent_id"] in {"cluster_tuning", "spark_rca", "hitl_demo"}:
            assert agent["mode"] == "local"
            assert agent["transport"] == "in_process"

    one = client.get("/api/v1/directory/agents/spark_rca")
    assert one.status_code == 200, one.text
    assert one.json()["agent_id"] == "spark_rca"

    missing = client.get("/api/v1/directory/agents/no_such_agent")
    assert missing.status_code == 404


def test_directory_register_upsert(client: TestClient):
    res = client.post(
        "/api/v1/directory/register",
        json={
            "agent_id": "heartbeat_peer",
            "mode": "remote",
            "transport": "http",
            "endpoint": "https://example.invalid",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["agent_id"] == "heartbeat_peer"


def test_directory_json_overlay_remote(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "EDIM_AGENT_DIRECTORY_JSON",
        json.dumps(
            {
                "external_helper": {
                    "mode": "remote",
                    "transport": "http",
                    "endpoint": "https://example.invalid",
                    "invoke_path": "/api/v1/agents/external_helper/invoke",
                    "healthy": True,
                }
            }
        ),
    )
    listed = client.get("/api/v1/directory/agents")
    assert listed.status_code == 200
    by_id = {a["agent_id"]: a for a in listed.json()["agents"]}
    assert "external_helper" in by_id
    assert by_id["external_helper"]["mode"] == "remote"
    assert by_id["external_helper"]["endpoint"] == "https://example.invalid"
