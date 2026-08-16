---
description: FastAPI routes and schemas for edim-dde-api
applyTo: "**/routes.py,**/schemas.py,**/main.py"
---

# API host conventions

- Routes invoke agents and project to Pydantic schemas — no diagnosis logic in routes.
- Persist via RecommendationStore with `agent_id`; agent-scoped list/get/PATCH.
- Best-effort `_persist_*`: never fail HTTP success because store/index failed.
- Bound large blobs in **stored** response copies; HTTP can still return full packs.
- Do not leak `llm_raw`, internal sizing fields, or full state bags.
- Health: report plane backend names only — never secrets or tokens.
- New endpoints: update schemas + e2e tests + env/docs if new `EDIM_*` knobs appear.
