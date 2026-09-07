"""ADR-001 Phase 3 generic invoke + Phase 5 directory register."""

from __future__ import annotations

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


def test_generic_invoke_compose_parent(client: TestClient):
    res = client.post(
        "/api/v1/agents/compose_parent/invoke",
        json={"input": {"request_id": "api-rid-1"}},
        headers={"X-Request-Id": "api-rid-1"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["agent_id"] == "compose_parent"
    assert body["request_id"] == "api-rid-1"
    assert body["status"] == "completed"
    assert body["state"].get("leaf_greeting") == "composed-demo"


def test_generic_invoke_unknown(client: TestClient):
    res = client.post("/api/v1/agents/no_such_agent/invoke", json={"input": {}})
    assert res.status_code == 404


def test_directory_register_and_list(client: TestClient):
    reg = client.post(
        "/api/v1/directory/register",
        json={
            "agent_id": "heartbeat_peer",
            "mode": "remote",
            "transport": "http",
            "endpoint": "https://example.invalid",
            "invoke_path": "/api/v1/agents/heartbeat_peer/invoke",
            "healthy": True,
        },
    )
    assert reg.status_code == 200, reg.text
    assert reg.json()["agent_id"] == "heartbeat_peer"

    listed = client.get("/api/v1/directory/agents")
    assert listed.status_code == 200
    ids = {a["agent_id"] for a in listed.json()["agents"]}
    assert "heartbeat_peer" in ids
    assert "compose_parent" in ids
    assert "compose_leaf" in ids
