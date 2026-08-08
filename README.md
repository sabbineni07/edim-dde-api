# EDIM DDE API

Thin **FastAPI** app. Agents and tools live in
[`edim-dde-domain`](../edim-dde-domain); graphs run via
[`edim-dde-ai`](../edim-dde-ai).

**Docs:** [Stack engineer guide](../edim-dde-domain/docs/README.md) · [Endpoints](../edim-dde-domain/docs/api/endpoints.md) · [Configuration](../edim-dde-domain/docs/api/configuration.md) · [**Deploy & hosting**](../edim-dde-domain/docs/api/deploy-and-hosting.md)

```text
Client → edim-dde-api (HTTP)
              │  CORS + DatabricksUserTokenMiddleware
              │  lifespan: bootstrap_agents + Foundry LLM provider
              ▼
         edim-dde-ai create_agent(...).invoke(...)  (via asyncio.to_thread)
```

## Layout

```text
src/edim_dde_api/
  main.py         # lifespan, CORS, LLM, exception handlers
  middleware.py   # Apps user OAuth → ContextVar
  routes.py       # /health, /api/v1/rca/analyze, /api/v1/recommendations
  schemas.py      # request + response Pydantic models (OpenAPI)
deploy/
  databricks-app/ # app.yaml + requirements (default host)
  docker/         # portable Dockerfile (ACA / AKS / …)
  scripts/        # build_vendor_wheels.sh
```

## Deploy (Databricks Apps default)

```bash
./deploy/scripts/build_vendor_wheels.sh
# Edit deploy/databricks-app/app.yaml REPLACE_* values (no secrets in git)
# Sync deploy/databricks-app/ to the workspace App and deploy
```

Full runbook: [Deploy & hosting](../edim-dde-domain/docs/api/deploy-and-hosting.md).
## Setup

```bash
cd /Users/sabbineni/projects/edim/edim-dde-api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"
# Domain env (Databricks + Foundry) — see edim-dde-domain/.env.example
pytest -q
```

## CORS

Browser origins are an explicit allow-list (no `*` + credentials):

```bash
export EDIM_CORS_ORIGINS=https://my-app.example,http://localhost:4200
```

Unset / empty → no cross-origin browser access (fine for curl / same-origin).

## Run

```bash
# Local: az login for SQL + Foundry (or set AZURE_CLIENT_* from Key Vault in prod)
uvicorn edim_dde_api.main:app --reload --port 8080
```

```bash
curl -s http://127.0.0.1:8080/api/v1/recommendations \
  -H 'content-type: application/json' \
  -d '{"job_id":"123","cluster_id":"456","include_explanation":false}'
```

Versioned API surface:

| Method | Path | Response model |
|--------|------|----------------|
| GET | `/health` | status + agents |
| POST | `/api/v1/rca/analyze` | `RcaResponse` |
| POST | `/api/v1/recommendations` | `TuningResponse` |

On Databricks Apps, the gateway forwards `X-Forwarded-Access-Token`; middleware binds
it for SQL. `Authorization: Bearer` is not used as a Databricks token.
