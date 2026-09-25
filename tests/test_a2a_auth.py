"""A2A AuthZ gate tests (interim EDIM_A2A_TOKEN)."""

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


def test_invoke_open_when_token_unset(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("EDIM_A2A_TOKEN", raising=False)
    res = client.post(
        "/api/v1/agents/compose_parent/invoke",
        json={"input": {}},
    )
    assert res.status_code == 200, res.text


def test_invoke_requires_token_when_set(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EDIM_A2A_TOKEN", "secret-a2a")
    denied = client.post(
        "/api/v1/agents/compose_parent/invoke",
        json={"input": {}},
    )
    assert denied.status_code == 401, denied.text

    ok = client.post(
        "/api/v1/agents/compose_parent/invoke",
        json={"input": {}},
        headers={"Authorization": "Bearer secret-a2a"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["state"].get("leaf_greeting") == "composed-demo"

    ok_hdr = client.post(
        "/api/v1/agents/compose_leaf/invoke",
        json={"input": {"name": "z"}},
        headers={"X-Edim-A2A-Token": "secret-a2a"},
    )
    assert ok_hdr.status_code == 200, ok_hdr.text


def test_directory_register_requires_token(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EDIM_A2A_TOKEN", "secret-a2a")
    denied = client.post(
        "/api/v1/directory/register",
        json={
            "agent_id": "peer",
            "mode": "remote",
            "transport": "http",
            "endpoint": "https://example.invalid",
        },
    )
    assert denied.status_code == 401

    ok = client.post(
        "/api/v1/directory/register",
        json={
            "agent_id": "peer",
            "mode": "remote",
            "transport": "http",
            "endpoint": "https://example.invalid",
        },
        headers={"Authorization": "Bearer secret-a2a"},
    )
    assert ok.status_code == 200, ok.text
