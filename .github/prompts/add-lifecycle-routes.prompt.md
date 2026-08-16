---
name: add-lifecycle-routes
description: Add RecommendationStore persist + list/get/PATCH routes for a product agent
agent: agent
argument-hint: Agent id and existing analyze/recommend route to hook
---

# Add lifecycle HTTP routes

Mirror cluster_tuning / spark_rca:

1. After successful agent invoke, best-effort `_persist_*` → RecommendationStore (`proposed`)
2. Surface optional `recommendation_id` / `recommendation_status` on the response schema
3. Agent-scoped `GET/PATCH /api/v1/{agent}/recommendations` (and get-by-id)
4. Enforce `agent_id` on get/patch so records cannot be read cross-agent
5. Bound large fields in **stored** response (prompt context strings, huge packs) while HTTP may return full data
6. E2E TestClient coverage: persist, list, patch, cross-agent 404
7. Update endpoint/env docs if needed

Never fail the primary HTTP success path because persist failed — log and continue.
