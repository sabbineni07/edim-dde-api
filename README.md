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
  routes.py       # /health, /api/v1/rca/analyze, /api/v1/cluster_tuning/recommend
  schemas.py      # request + response Pydantic models (OpenAPI)
deploy/
  databricks-app/ # app.yaml + requirements (default host)
  docker/         # portable Dockerfile (ACA / AKS / …)
  scripts/        # build_vendor_wheels.sh
```

## Deploy (Databricks Apps default)

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

Full runbook (Apps console / CLI / CI, packaging Options A–D): [Deploy & hosting §5](../edim-dde-domain/docs/api/deploy-and-hosting.md#5-deploy--databricks-apps-default).

## Docker Compose (API + Postgres) — local E2E

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
