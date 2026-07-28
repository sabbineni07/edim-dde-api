# EDIM DDE API

Thin **FastAPI** app. Agents and tools live in
[`edim-dde-domain`](../edim-dde-domain); graphs run via
[`edim-dde-ai`](../edim-dde-ai).

```text
Client → edim-dde-api (HTTP)
              │
              ▼
         edim-dde-domain.bootstrap_agents()
              │
              ▼
         edim-dde-ai create_agent(...).invoke(...)
              │
              ├─ domain tools   (collect evidence / metrics)
              └─ domain logic   (classify, size, explain)
```

## Layout

```text
src/edim_dde_api/
  main.py       # lifespan → bootstrap_agents()
  routes.py     # POST /api/rca/analyze, /api/recommendations
  schemas.py    # request bodies
  bootstrap.py  # re-exports domain bootstrap (compat)
```

No agent YAML or tools here — those are in `edim-dde-domain`.

## Setup

```bash
cd /Users/sabbineni/projects/edim/edim-dde-api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"
pytest -q
```

## Run

```bash
uvicorn edim_dde_api.main:app --reload --port 8080
```

Docs: http://127.0.0.1:8080/docs

```bash
curl -s http://127.0.0.1:8080/api/rca/analyze \
  -H 'content-type: application/json' \
  -d '{"job_run_id":"jr-1","error_text":"OutOfMemoryError: Java heap space"}'
```
