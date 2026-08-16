---
name: add-api-e2e-test
description: Add FastAPI TestClient e2e coverage for a route without live cloud deps
agent: agent
argument-hint: Route path and assertions needed
---

# Add API e2e test

- Use existing fixtures / stub LLM / evidence or metrics overrides
- Assert status codes, schema fields, and non-leakage of internal state keys
- If lifecycle is involved, assert recommendation list/get/patch and agent scoping
- Keep tests dry (no real Databricks/Foundry required)

Follow `tests/test_agents_e2e.py` patterns.
