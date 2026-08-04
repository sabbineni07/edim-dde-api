# Changelog — edim-dde-api

## 1.0.0 — 2026-07-31 (Release 1 / Phase 0)

### Added
- Key Vault bootstrap on API lifespan
- LangSmith-oriented `request_id` / run config on agent invokes
- `configure_observability_from_env()` on lifespan (`EDIM_OBSERVABILITY`)
- `configure_state_store_from_env()` + `sync_registered_agents_to_store()` on lifespan (`EDIM_STATE_STORE`)
- `configure_retrieval_from_env()` on lifespan (`EDIM_RETRIEVAL`)
- `/health` includes `version`, `observability`, `state_store`, and `retrieval`
- `POST /api/v1/knowledge/ingest` — Acceptance-gated curated upsert (`accepted=true` + optional `summary`)

### Notes
- R1 version alignment with domain + ai. Internal index publish is ops-owned.
- Default store is in-memory; use Postgres locally and Cosmos when deployed (see domain docs `platform/state-store.md`).
- Default retrieval is `none`; use FAISS locally / Volume and Azure AI Search when deployed (`platform/retrieval-and-rag.md`).