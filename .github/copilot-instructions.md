# EDIM DDE API — GitHub Copilot instructions

> **Team source of truth for VS Code + GitHub Copilot.**  
> Keep the shared “EDIM DDE practices” section aligned with sibling repos `edim-dde-ai` and `edim-dde-domain`.  
> Deep design: domain MkDocs + this host’s README. Keep this file short and actionable.

This package is the **thin FastAPI host**: HTTP schemas, routes, lifespan plane wiring, middleware. It invokes agents via `edim-dde-ai.create_agent` after `edim-dde-domain` bootstrap. No product diagnosis logic belongs here.

---

## Shared EDIM DDE practices (keep aligned across repos)

### Separation of concerns

- **API = HTTP boundary only** — agent graphs, SQL, classify/validate, prompts live in domain/ai.
- Persist through **RecommendationStore** (framework), not bespoke tables per agent when lifecycle already exists.
- **Fail soft** on secondary persist/index/web failures: log and still return a successful analysis when the agent completed.
- Never dump full LangGraph state bags to clients.

### Design patterns (prefer these)

| Prefer | Use for |
|--------|---------|
| Facade | Stable Pydantic response models (`RcaResponse`, `TuningResponse`) |
| Strategy / Null | Planes configured at lifespan (`none` / memory / postgres / …) |
| Best-effort wrapper | `_persist_*` helpers that catch and log |
| Agent-scoped routes | `/api/v1/{agent}/recommendations` — do not cross-read other agents’ ids |

### Code quality

- **DRY**: shared request-id / token middleware; mirror persist + list/get/PATCH patterns across agents.
- **Docstrings**: module Business purpose; route handlers describe HTTP contract; persist helpers document what is stored vs omitted.
- **Inline comments**: auth/token forwarding, bounded store payloads, CORS/Apps quirks.

### Testing & validation

- API e2e with TestClient + domain bootstrap + stub LLM / evidence overrides.
- Assert response contract fields and that internal keys (`llm_raw`, sizing internals) do not leak.
- **Dry** host tests in CI; **live** Foundry/Databricks only in explicit validation runs.

### Documentation

- Endpoint and env docs should stay in sync when adding routes or planes (`EDIM_*` vars).

---

## This package (`edim-dde-api`) — boundaries

### Lifespan / planes

Wire from env (do not hardcode secrets):

- Observability, state store, recommendation store, retrieval, web search
- Domain `bootstrap_agents`
- Optional Foundry LLM provider

### HTTP rules

- Versioned routes under `/api/v1/...`
- Project agent invoke results into **schemas** — missing `result` → 500, not a raw state dump
- Recommendation persist: exclude huge request blobs where needed; store **bounded** snapshots for indexing (e.g. RCA evidence) while the HTTP response may still return the full pack
- Health reports plane names (`recommendation_store`, `web_search`, …) without secrets

### Do not

- Embed Spark/Databricks SQL or LLM prompt construction in routes
- Bypass RecommendationStore for “temporary” lifecycle tracking
- Share recommendation get/PATCH across agents without `agent_id` checks
