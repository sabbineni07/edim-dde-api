# EDIM DDE API

Thin **FastAPI** app. Agents and tools live in
[`edim-dde-domain`](../edim-dde-domain); graphs run via
[`edim-dde-ai`](../edim-dde-ai).

**Docs:** [Stack engineer guide](../edim-dde-domain/docs/README.md) · [Endpoints](../edim-dde-domain/docs/api/endpoints.md) · [Configuration](../edim-dde-domain/docs/api/configuration.md) · [**Deployment targets and release runbook](../edim-dde-domain/docs/api/deployment-targets.md) · [Deploy & hosting compatibility runbook](../edim-dde-domain/docs/api/deploy-and-hosting.md)

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
  routes.py       # /health, /api/v1/rca/analyze, /api/v1/cluster_tuning/recommend
  schemas.py      # request + response Pydantic models (OpenAPI)
deploy/
  databricks-app/ # app.yaml + requirements (compatibility host)
  docker/         # ACA Native Dockerfiles
  scripts/        # build_vendor_wheels.sh
```

## Select a deployment target

| Target | Status | Runtime |
|---|---|---|
| ACA Native | **Standard** | `uvicorn edim_dde_api.main:app` |
| Standalone Agent Server on ACA | Optional | LangGraph Agent Server + graph manifest |
| Full self-hosted LangSmith Deployment on AKS | Optional | LangSmith control plane + Agent Server |
| Databricks Apps | Compatibility | `uvicorn edim_dde_api.main:app` |

Start with the [Deployment targets and release runbook](../edim-dde-domain/docs/api/deployment-targets.md).
It explains the shared YAML artifact, identity model, packaging steps, target
configuration, rollout, validation, and rollback. The Databricks Apps commands
below remain for existing Apps workloads.

## Deploy (Databricks Apps compatibility path)

```bash
cd edim-dde-api
make help
make vendor-wheels
# Edit deploy/databricks-app/app.yaml REPLACE_* (no secrets in git)
make apps-create APP_NAME=edim-dde-api-dev
# Grant App SP → Key Vault Secrets User (key-vault-bootstrap.md §7)
make apps-sync  APP_NAME=edim-dde-api-dev WS_SOURCE=/Workspace/Users/<you>/apps/edim-dde-api-dev
make apps-deploy APP_NAME=edim-dde-api-dev WS_SOURCE=/Workspace/Users/<you>/apps/edim-dde-api-dev
```

Engineer MkDocs guide (`/guide`) is **local Docker only** — not deployed to Apps:

```bash
make guide-site && make compose-up
# open http://127.0.0.1:8080/guide/
```

Apps runbook (console / CLI / CI, packaging Options A–D): [Deploy & hosting](../edim-dde-domain/docs/api/deploy-and-hosting.md) §5.

## Docker — local E2E

**A. API on laptop + Postgres in Docker** (use this when `az login` must run on the host):

```bash
cd edim-dde-api
az login
# Foundry/Databricks vars in ../edim-dde-domain/.env
make host-run            # starts Postgres container + uvicorn on :8080
# make pg-down           # stop Postgres when done
```

**B. API + Postgres both in Docker** (Foundry via `.env` / SP — host `az login` does not enter the container):

```bash
cd edim-dde-api
# Foundry vars in ../edim-dde-domain/.env
make e2e-local           # compose-up + dry health/tuning/RCA
# or:
make compose-up && make e2e-dry && make compose-down
```

Postgres = control-plane StateStore only. Guide: [Deploy §6.1](../edim-dde-domain/docs/api/deploy-and-hosting.md#61-docker-compose-api--postgres--recommended-locally) · [Live smoke](../edim-dde-domain/docs/contribute/live-smoke-test.md).
## Setup

```bash
cd edim-dde-api
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
# Local: az login for SQL + Foundry (or set EDIM_FOUNDRY_* from Key Vault in prod)
uvicorn edim_dde_api.main:app --reload --port 8080
```

```bash
curl -s http://127.0.0.1:8080/api/v1/cluster_tuning/recommend \
  -H 'content-type: application/json' \
  -d '{"job_id":"123","cluster_id":"456","include_explanation":false}'
```

Versioned API surface:

| Method | Path | Response model |
|--------|------|----------------|
| GET | `/health` | status + agents |
| POST | `/api/v1/rca/analyze` | `RcaResponse` |
| POST | `/api/v1/cluster_tuning/recommend` | `TuningResponse` |

**Breaking:** `/api/v1/recommendations` is not registered (404). Use `/api/v1/cluster_tuning/recommend`.

Optional `X-Request-Id` is echoed on the response; stdlib logs include `[request_id=…]`. Failures log a redacted stack once at the HTTP boundary; JSON `detail` stays short.

On Databricks Apps, the gateway forwards `X-Forwarded-Access-Token`; middleware binds
it for SQL. `Authorization: Bearer` is not used as a Databricks token.
