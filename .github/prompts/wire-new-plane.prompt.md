---
name: wire-new-plane
description: Wire a new edim-dde-ai plane into API lifespan and health
agent: agent
argument-hint: Plane name and EDIM_* env vars
---

# Wire a framework plane into the API host

1. Call `configure_*_from_env` (or set provider) in FastAPI lifespan
2. Expose backend name on `/health` without secrets
3. Document env vars in `.env.example` / docs if this repo tracks them
4. Default to disabled/`none` when unset
5. Add a small test asserting health key presence when possible

Do not implement provider SDKs here — those belong in `edim-dde-ai`.
