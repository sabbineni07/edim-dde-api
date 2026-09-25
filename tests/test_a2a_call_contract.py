"""ADR-002 generic invoke multi-turn + async_accept."""

from __future__ import annotations

import pytest
from edim_dde_ai import set_llm_provider
from edim_dde_ai.a2a.bindings import clear_runtime_bindings
from edim_dde_ai.a2a.turns import clear_conversation_turns
from edim_dde_ai.content.registry import clear_llm_provider
from edim_dde_api.a2a_tasks import clear_a2a_tasks
from edim_dde_domain import bootstrap_agents, reset_bootstrap
from edim_dde_domain.sources import clear_sources
from edim_dde_domain.testing import DomainStubLLM
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _agents_with_stub_llm():
    clear_sources()
    reset_bootstrap()
    clear_runtime_bindings()
    clear_conversation_turns()
    clear_a2a_tasks()
    set_llm_provider(DomainStubLLM())
    bootstrap_agents()
    yield
    reset_bootstrap()
    clear_llm_provider()
    clear_sources()
    clear_runtime_bindings()
    clear_conversation_turns()
    clear_a2a_tasks()


@pytest.fixture
def client(_agents_with_stub_llm):
    from edim_dde_api.main import app

    with TestClient(app) as test_client:
        set_llm_provider(DomainStubLLM())
        yield test_client


def test_invoke_multi_turn_a2a_partner(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("EDIM_A2A_TOKEN", raising=False)
    t1 = client.post(
        "/api/v1/agents/a2a_partner/invoke",
        json={"conversation_id": "c-api-1", "input": {"message": "one"}},
    )
    assert t1.status_code == 200, t1.text
    body1 = t1.json()
    assert body1["status"] == "completed"
    assert body1["conversation_id"] == "c-api-1"
    assert body1["state"]["turn_count"] == 1

    t2 = client.post(
        "/api/v1/agents/a2a_partner/invoke",
        json={"conversation_id": "c-api-1", "input": {"message": "two"}},
    )
    assert t2.status_code == 200, t2.text
    assert t2.json()["state"]["turn_count"] == 2


def test_async_accept_and_poll(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("EDIM_A2A_TOKEN", raising=False)
    res = client.post(
        "/api/v1/agents/a2a_partner/invoke",
        json={
            "conversation_id": "c-async",
            "async_accept": True,
            "input": {"message": "later"},
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "running"
    assert body["task_id"]
    poll = client.get(f"/api/v1/agents/tasks/{body['task_id']}")
    assert poll.status_code == 200, poll.text
    assert poll.json()["status"] == "running"
