"""ADR-002 durable async: accept → worker → poll completed."""

from __future__ import annotations

import time

import pytest
from edim_dde_ai import set_llm_provider
from edim_dde_ai.a2a.bindings import clear_runtime_bindings
from edim_dde_ai.a2a.tasks import FileTaskStore, clear_a2a_tasks, set_task_store
from edim_dde_ai.a2a.turns import clear_conversation_turns
from edim_dde_ai.content.registry import clear_llm_provider
from edim_dde_api.a2a_tasks import shutdown_a2a_workers
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
    shutdown_a2a_workers(wait=True)
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


def _poll_completed(client: TestClient, task_id: str, *, timeout_s: float = 5.0) -> dict:
    deadline = time.time() + timeout_s
    last = {}
    while time.time() < deadline:
        poll = client.get(f"/api/v1/agents/tasks/{task_id}")
        assert poll.status_code == 200, poll.text
        last = poll.json()
        if last.get("status") in {"completed", "input_needed", "error"}:
            return last
        time.sleep(0.05)
    raise AssertionError(f"task did not finish: {last!r}")


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


def test_async_accept_worker_completes(client: TestClient, monkeypatch: pytest.MonkeyPatch):
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
    done = _poll_completed(client, body["task_id"])
    assert done["status"] == "completed"
    assert done["state"].get("turn_count") == 1
    assert done["state"].get("reply") == "ack-later"


def test_file_task_store_survives_reread(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EDIM_A2A_TASK_STORE", "file")
    monkeypatch.setenv("EDIM_A2A_TASK_DIR", str(tmp_path))
    store = FileTaskStore(tmp_path)
    set_task_store(store)
    from edim_dde_ai.a2a.tasks import accept_task, get_task

    rec = accept_task(
        agent_id="a2a_partner",
        request_id="r1",
        conversation_id="c1",
        payload={"message": "x"},
    )
    # New store instance on same dir (simulates process restart read)
    set_task_store(FileTaskStore(tmp_path))
    loaded = get_task(rec["task_id"])
    assert loaded is not None
    assert loaded["agent_id"] == "a2a_partner"
    assert loaded["payload"]["message"] == "x"
    clear_a2a_tasks()
