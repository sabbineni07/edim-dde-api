# EDIM DDE API

Thin **FastAPI** app. Agents and tools live in
[`edim-dde-domain`](../edim-dde-domain); graphs run via
[`edim-dde-ai`](../edim-dde-ai).

```text
Client → edim-dde-api (HTTP)
              │  CORS + DatabricksUserTokenMiddleware
              │  lifespan: bootstrap_agents + Foundry LLM provider
              ▼
         edim-dde-ai create_agent(...).invoke(...)
```

## Layout

```text
src/edim_dde_api/
  main.py         # lifespan, CORS, LLM, exception handlers
  middleware.py   # Apps user OAuth → ContextVar
  routes.py       # /health, /api/rca/analyze, /api/recommendations
  schemas.py
```

## Setup

```bash
cd /Users/sabbineni/projects/edim/edim-dde-api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"
# Domain env (Databricks + Foundry) — see edim-dde-domain/.env.example
pytest -q
```

## Run

```bash
# Local: az login for SQL + Foundry (or set AZURE_CLIENT_* from Key Vault in prod)
uvicorn edim_dde_api.main:app --reload --port 8080
```

```bash
curl -s http://127.0.0.1:8080/api/recommendations \
  -H 'content-type: application/json' \
  -d '{"job_id":"123","cluster_id":"456","include_explanation":false}'
```

On Databricks Apps, the gateway forwards `X-Forwarded-Access-Token`; middleware binds it for SQL.
