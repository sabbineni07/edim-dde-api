#!/usr/bin/env bash
# Local / Compose end-to-end dry smoke against a running API.
# Skips Databricks SQL (metrics / evidence_pack overrides). Requires Foundry
# (or fails with 503) — see docs/contribute/live-smoke-test.md
#
# Usage:
#   ./deploy/scripts/e2e_smoke.sh              # BASE default http://127.0.0.1:8080
#   BASE=http://127.0.0.1:8080 ./deploy/scripts/e2e_smoke.sh
#   make e2e-dry                               # from edim-dde-api/
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:8080}"
BASE="${BASE%/}"
PYTHON="${PYTHON:-python3}"
EXPECT_STORE="${EXPECT_STATE_STORE:-postgres}"
WAIT_SEC="${WAIT_SEC:-90}"

echo "==> Waiting for $BASE/health (up to ${WAIT_SEC}s)"
deadline=$((SECONDS + WAIT_SEC))
while true; do
  if curl -sfS "$BASE/health" >/tmp/edim-e2e-health.json 2>/dev/null; then
    break
  fi
  if (( SECONDS >= deadline )); then
    echo "error: health not ready at $BASE/health" >&2
    exit 1
  fi
  sleep 2
done

echo "==> Health"
"$PYTHON" - <<'PY'
import json, sys
h = json.load(open("/tmp/edim-e2e-health.json"))
print(json.dumps(h, indent=2))
assert h.get("status") == "ok", h
agents = set(h.get("agents") or [])
missing = {"cluster_tuning", "spark_rca"} - agents
assert not missing, f"missing agents: {missing}"
print("health ok; agents present")
PY

if [[ -n "${EXPECT_STORE}" ]]; then
  store="$("$PYTHON" -c 'import json; print(json.load(open("/tmp/edim-e2e-health.json")).get("state_store",""))')"
  echo "state_store=$store (expect $EXPECT_STORE)"
  if [[ "$store" != "$EXPECT_STORE" ]]; then
    echo "error: expected state_store=$EXPECT_STORE, got $store" >&2
    exit 1
  fi
fi

echo "==> Dry cluster_tuning (SQL skipped via metrics override)"
curl -sfS "$BASE/api/v1/cluster_tuning/recommend" \
  -H 'content-type: application/json' \
  -H 'X-Request-Id: e2e-dry-tuning-001' \
  -d '{
    "job_id": "dry-job-1",
    "cluster_id": "dry-cluster-1",
    "include_explanation": false,
    "metrics": {
      "azure_worker_vm_size": "Standard_E8s_v3",
      "max_worker_nodes_provisioned": 16,
      "avg_worker_nodes_consumed": 4.0,
      "p99_worker_nodes_consumed": 5.0,
      "peak_worker_cpu_utilization_pct": 20,
      "peak_worker_memory_utilization_pct": 25,
      "avg_worker_cpu_utilization_pct": 15,
      "avg_worker_memory_utilization_pct": 18,
      "driver_node_count": 1
    }
  }' | "$PYTHON" -m json.tool >/tmp/edim-e2e-tuning.json
"$PYTHON" - <<'PY'
import json
d = json.load(open("/tmp/edim-e2e-tuning.json"))
assert "recommendation" in d or d.get("status"), d
print("dry tuning ok")
PY

echo "==> Dry spark_rca (SQL skipped via evidence_pack)"
curl -sfS "$BASE/api/v1/rca/analyze" \
  -H 'content-type: application/json' \
  -H 'X-Request-Id: e2e-dry-rca-001' \
  -d '{
    "job_run_id": "dry-jr-1",
    "job_id": "dry-job-1",
    "evidence_pack": {
      "job_run_id": "dry-jr-1",
      "evidence": [
        {"ref": "e1", "excerpt": "Executor OutOfMemoryError: Java heap space"}
      ],
      "raw_anchors": {
        "failure_reason": "Executor OutOfMemoryError: Java heap space"
      }
    }
  }' | "$PYTHON" -m json.tool >/tmp/edim-e2e-rca.json
"$PYTHON" - <<'PY'
import json
d = json.load(open("/tmp/edim-e2e-rca.json"))
assert d.get("root_cause") or d.get("status"), d
print("dry rca ok")
PY

echo ""
echo "E2E dry smoke passed against $BASE"
echo "  (Postgres StateStore + Foundry; Databricks SQL not exercised)"
echo "  Live SQL: see docs/contribute/live-smoke-test.md §5 with BASE=$BASE"
