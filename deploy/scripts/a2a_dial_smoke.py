#!/usr/bin/env python3
"""Two-runtime A2A dial smoke (ADR-001 / ADR-002).

1. Peer uvicorn (Runtime B) with ``EDIM_A2A_TOKEN``
2. ``call_agent`` / dial to ``a2a_partner`` — two turns on one conversation_id
3. Auth negative check
4. Optional legacy ``compose_parent`` remote overlay still exercised

Usage (from edim-dde-api)::

    PYTHONPATH=src:../edim-dde-ai/src:../edim-dde-domain/src \\
      python deploy/scripts/a2a_dial_smoke.py

Exit 0 on success. Does not require Foundry/Databricks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AI_SRC = ROOT.parent / "edim-dde-ai" / "src"
DOMAIN_SRC = ROOT.parent / "edim-dde-domain" / "src"
API_SRC = ROOT / "src"

for path in (API_SRC, AI_SRC, DOMAIN_SRC):
    p = str(path)
    if p not in sys.path:
        sys.path.insert(0, p)

TOKEN = os.environ.get("EDIM_A2A_TOKEN") or "a2a-smoke-token"
PEER_PORT = int(os.environ.get("EDIM_A2A_SMOKE_PEER_PORT") or "18081")
PEER_BASE = f"http://127.0.0.1:{PEER_PORT}"


def _wait_health(base: str, *, timeout_s: float = 30.0) -> None:
    deadline = time.time() + timeout_s
    url = f"{base}/health"
    last = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as resp:  # noqa: S310
                body = json.loads(resp.read().decode("utf-8"))
            if body.get("status") == "ok":
                return
            last = str(body)
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        time.sleep(0.25)
    raise RuntimeError(f"peer health not ready at {url}: {last}")


def _post_invoke(agent_id: str, body: dict, *, token: str | None = TOKEN) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{PEER_BASE}/api/v1/agents/{agent_id}/invoke",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15.0) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    env = os.environ.copy()
    env["EDIM_A2A_TOKEN"] = TOKEN
    env["EDIM_ENV"] = env.get("EDIM_ENV") or "dev"
    env["EDIM_STATE_STORE"] = env.get("EDIM_STATE_STORE") or "memory"
    env["EDIM_CHECKPOINTER"] = env.get("EDIM_CHECKPOINTER") or "memory"
    env["EDIM_RECOMMENDATION_STORE"] = env.get("EDIM_RECOMMENDATION_STORE") or "memory"
    env["EDIM_OBSERVABILITY"] = env.get("EDIM_OBSERVABILITY") or "none"
    env["EDIM_AGENT_RESOLVE"] = "auto"
    py_path = os.pathsep.join(
        [str(API_SRC), str(AI_SRC), str(DOMAIN_SRC), env.get("PYTHONPATH", "")]
    )
    env["PYTHONPATH"] = py_path

    peer = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-m",
            "uvicorn",
            "edim_dde_api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(PEER_PORT),
            "--log-level",
            "warning",
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        _wait_health(PEER_BASE)

        # --- ADR-002: two turns on the same conversation_id via HTTP ---
        turn1 = _post_invoke(
            "a2a_partner",
            {
                "conversation_id": "smoke-conv-1",
                "input": {"message": "hello"},
            },
        )
        if turn1.get("status") != "completed":
            raise RuntimeError(f"turn1 status={turn1.get('status')!r}")
        if turn1.get("conversation_id") != "smoke-conv-1":
            raise RuntimeError(f"turn1 conversation_id={turn1.get('conversation_id')!r}")
        if (turn1.get("state") or {}).get("turn_count") != 1:
            raise RuntimeError(f"turn1 state={turn1.get('state')!r}")

        turn2 = _post_invoke(
            "a2a_partner",
            {
                "conversation_id": "smoke-conv-1",
                "input": {"message": "again"},
            },
        )
        if (turn2.get("state") or {}).get("turn_count") != 2:
            raise RuntimeError(f"turn2 expected turn_count=2 got {turn2!r}")

        # async_accept stub
        accepted = _post_invoke(
            "a2a_partner",
            {
                "conversation_id": "smoke-async",
                "async_accept": True,
                "input": {"message": "later"},
            },
        )
        if accepted.get("status") != "running" or not accepted.get("task_id"):
            raise RuntimeError(f"async_accept failed: {accepted!r}")
        task_req = urllib.request.Request(
            f"{PEER_BASE}/api/v1/agents/tasks/{accepted['task_id']}",
            headers={"Authorization": f"Bearer {TOKEN}"},
            method="GET",
        )
        with urllib.request.urlopen(task_req, timeout=5.0) as resp:  # noqa: S310
            task_body = json.loads(resp.read().decode("utf-8"))
        if task_body.get("status") != "running":
            raise RuntimeError(f"task poll failed: {task_body!r}")

        # --- call_agent from Runtime A with remote binding ---
        overlay = {
            "a2a_partner": {
                "mode": "remote",
                "transport": "http",
                "endpoint": PEER_BASE,
                "invoke_path": "/api/v1/agents/a2a_partner/invoke",
                "healthy": True,
            },
            "compose_leaf": {
                "mode": "remote",
                "transport": "http",
                "endpoint": PEER_BASE,
                "invoke_path": "/api/v1/agents/compose_leaf/invoke",
                "healthy": True,
            },
        }
        os.environ["EDIM_A2A_TOKEN"] = TOKEN
        os.environ["EDIM_AGENT_DIRECTORY_JSON"] = json.dumps(overlay)
        os.environ["EDIM_AGENT_RESOLVE"] = "auto"
        os.environ.setdefault("EDIM_A2A_HTTP_RETRIES", "2")
        os.environ.setdefault("EDIM_A2A_HTTP_TIMEOUT_S", "15")

        from edim_dde_ai import create_agent, set_llm_provider
        from edim_dde_ai.a2a import call_agent, clear_conversation_turns, clear_runtime_bindings
        from edim_dde_ai.content.registry import clear_llm_provider
        from edim_dde_domain import bootstrap_agents, reset_bootstrap
        from edim_dde_domain.sources import clear_sources
        from edim_dde_domain.testing import DomainStubLLM

        clear_sources()
        reset_bootstrap()
        clear_runtime_bindings()
        clear_conversation_turns()
        set_llm_provider(DomainStubLLM())
        bootstrap_agents()

        env1 = call_agent(
            "a2a_partner",
            {"message": "via-call"},
            conversation_id="call-conv-1",
            resolve="remote",
        )
        if env1.get("status") != "completed":
            raise RuntimeError(f"call_agent turn1={env1!r}")
        if (env1.get("state") or {}).get("turn_count") != 1:
            raise RuntimeError(f"call_agent turn1 count={env1!r}")

        env2 = call_agent(
            "a2a_partner",
            {"message": "via-call-2"},
            conversation_id="call-conv-1",
            resolve="remote",
        )
        if (env2.get("state") or {}).get("turn_count") != 2:
            raise RuntimeError(f"call_agent turn2={env2!r}")

        # Legacy compose_parent remote leaf still works
        out = create_agent("compose_parent").invoke({"request_id": "a2a-smoke-1"})
        if out.get("leaf_greeting") != "composed-demo":
            raise RuntimeError(f"compose_parent unexpected: {out!r}")

        # Negative: peer rejects missing token
        req = urllib.request.Request(
            f"{PEER_BASE}/api/v1/agents/a2a_partner/invoke",
            data=json.dumps({"input": {"message": "x"}}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:  # noqa: S310
                raise RuntimeError(f"expected 401 without token, got {resp.status}")
        except urllib.error.HTTPError as exc:
            if exc.code != 401:
                raise RuntimeError(f"expected 401 without token, got {exc.code}") from exc

        print(
            json.dumps(
                {
                    "status": "ok",
                    "peer": PEER_BASE,
                    "multi_turn": True,
                    "call_agent": True,
                    "async_accept": accepted["task_id"],
                    "leaf_greeting": out.get("leaf_greeting"),
                    "auth": "EDIM_A2A_TOKEN enforced",
                }
            )
        )
        return 0
    finally:
        peer.terminate()
        try:
            peer.wait(timeout=10)
        except subprocess.TimeoutExpired:
            peer.kill()
        try:
            clear_llm_provider()
            reset_bootstrap()
            clear_sources()
            clear_runtime_bindings()
            clear_conversation_turns()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "fail", "error": str(exc)}), file=sys.stderr)
        raise SystemExit(1) from exc
