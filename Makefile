# EDIM DDE API — recommended commands
# Usage: cd edim-dde-api && make <target>
#
# Engineer guide: ../edim-dde-domain/docs/api/deploy-and-hosting.md (§5 Apps, §6 Docker)
# Smoke: ../edim-dde-domain/docs/contribute/live-smoke-test.md

.PHONY: help vendor-wheels apps-create apps-sync apps-deploy apps-get apps-list \
	docker-build docker-run compose-up compose-down compose-ps compose-logs \
	e2e-health e2e-dry e2e-local clean-vendor

PYTHON ?= python3
APP_NAME ?= edim-dde-api-dev
WS_SOURCE ?=
EDIM_AI_PATH ?=
EDIM_DOMAIN_PATH ?=
DOCKER_IMAGE ?= edim-dde-api:local
BASE ?= http://127.0.0.1:8080
EXPECT_STATE_STORE ?= postgres

help: ## Show this help
	@echo "edim-dde-api — make targets"
	@echo ""
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'
	@echo ""
	@echo "Variables: APP_NAME=$(APP_NAME)  BASE=$(BASE)  EXPECT_STATE_STORE=$(EXPECT_STATE_STORE)"
	@echo ""
	@echo "Local E2E (Compose = API + Postgres StateStore):"
	@echo "  make compose-up && make e2e-dry && make compose-down"
	@echo "  (put Foundry/Databricks vars in ../edim-dde-domain/.env)"
	@echo ""
	@echo "Databricks Apps: make vendor-wheels && make apps-create … (docs §5)"

vendor-wheels: ## Build ai+domain+api wheels into deploy/databricks-app/vendor/
	@if [ -n "$(EDIM_AI_PATH)" ]; then export EDIM_AI_PATH="$(EDIM_AI_PATH)"; fi; \
	if [ -n "$(EDIM_DOMAIN_PATH)" ]; then export EDIM_DOMAIN_PATH="$(EDIM_DOMAIN_PATH)"; fi; \
	PYTHON="$(PYTHON)" ./deploy/scripts/build_vendor_wheels.sh

apps-create: ## Create Databricks App shell (APP_NAME)
	databricks apps create "$(APP_NAME)" --description "EDIM DDE API ($(APP_NAME))"

apps-list: ## List Databricks Apps
	databricks apps list

apps-get: ## Get one app (APP_NAME)
	databricks apps get "$(APP_NAME)"

apps-sync: ## Upload deploy/databricks-app → WS_SOURCE
	@test -n "$(WS_SOURCE)" || (echo "error: set WS_SOURCE=/Workspace/.../$(APP_NAME)" >&2; exit 1)
	@test -f deploy/databricks-app/requirements.vendor.txt || (echo "error: run make vendor-wheels first" >&2; exit 1)
	databricks workspace import-dir deploy/databricks-app "$(WS_SOURCE)" --overwrite

apps-deploy: ## Deploy APP_NAME from WS_SOURCE (SNAPSHOT)
	@test -n "$(WS_SOURCE)" || (echo "error: set WS_SOURCE=/Workspace/.../$(APP_NAME)" >&2; exit 1)
	databricks apps deploy "$(APP_NAME)" --source-code-path "$(WS_SOURCE)" --mode SNAPSHOT

docker-build: ## Build API image only (runs vendor-wheels first)
	$(MAKE) vendor-wheels
	docker build -f deploy/docker/Dockerfile -t "$(DOCKER_IMAGE)" .

docker-run: ## Run API image alone (no Postgres — prefer compose-up for E2E)
	docker run --rm -p 8080:8080 --env-file ../edim-dde-domain/.env "$(DOCKER_IMAGE)"

compose-up: ## Build & start API + Postgres StateStore
	$(MAKE) vendor-wheels
	docker compose up --build -d
	@echo ""
	@echo "API:      $(BASE)/health"
	@echo "Postgres: localhost:5432  user/db/password = edim/edim/edim"
	@echo "E2E dry:  make e2e-dry"
	@echo "Logs:     make compose-logs"

compose-down: ## Stop API + Postgres (keeps postgres volume edim_pg_data)
	docker compose down

compose-ps: ## Show compose service status
	docker compose ps

compose-logs: ## Tail API + Postgres logs
	docker compose logs -f api postgres

e2e-health: ## Wait for /health (BASE); assert state_store=postgres by default
	BASE="$(BASE)" EXPECT_STATE_STORE="$(EXPECT_STATE_STORE)" PYTHON="$(PYTHON)" \
		bash -c 'set -euo pipefail; \
		deadline=$$((SECONDS+90)); \
		while ! curl -sfS "$$BASE/health" >/tmp/edim-e2e-health.json; do \
		  if (( SECONDS >= deadline )); then echo "health timeout" >&2; exit 1; fi; \
		  sleep 2; \
		done; \
		$(PYTHON) -c "import json; h=json.load(open(\"/tmp/edim-e2e-health.json\")); print(h); assert h.get(\"status\")==\"ok\"; assert h.get(\"state_store\")==\"$(EXPECT_STATE_STORE)\", h"'

e2e-dry: ## Full dry E2E vs Compose/API (health + tuning + RCA; needs Foundry)
	BASE="$(BASE)" EXPECT_STATE_STORE="$(EXPECT_STATE_STORE)" PYTHON="$(PYTHON)" \
		./deploy/scripts/e2e_smoke.sh

e2e-local: ## compose-up + e2e-dry (one-shot local container E2E)
	$(MAKE) compose-up
	$(MAKE) e2e-dry BASE="$(BASE)" EXPECT_STATE_STORE="$(EXPECT_STATE_STORE)"

clean-vendor: ## Remove vendored wheels
	rm -rf deploy/databricks-app/vendor
	rm -f deploy/databricks-app/requirements.vendor.txt
