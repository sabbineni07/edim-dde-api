# EDIM DDE API — recommended commands
# Usage: cd edim-dde-api && make <target>
#
# Engineer guide: ../edim-dde-domain/docs/api/deploy-and-hosting.md (§5 Apps, §6 Docker)
# Smoke: ../edim-dde-domain/docs/contribute/live-smoke-test.md

.PHONY: help vendor-wheels vendor-wheels-win guide-site apps-create apps-sync apps-deploy apps-get apps-list \
	docker-build docker-run compose-up compose-down compose-ps compose-logs \
	pg-up pg-down pg-ps pg-wait host-run host-up \
	e2e-health e2e-dry e2e-local clean-vendor

PYTHON ?= python3
APP_NAME ?= edim-dde-api-dev
WS_SOURCE ?=
EDIM_AI_PATH ?=
EDIM_DOMAIN_PATH ?=
GIT_BASH ?= C:/Program Files/Git/bin/bash.exe
DOCKER_IMAGE ?= edim-dde-api:local
BASE ?= http://127.0.0.1:8080
EXPECT_STATE_STORE ?= postgres
# Host uvicorn (API on laptop + Postgres in Docker) — preferred when az login must run on the host
PORT ?= 8080
RELOAD ?= 1
DOMAIN_ENV ?= ../edim-dde-domain/.env
ROOT_DIR := $(abspath ..)
STATE_COMPOSE := $(ROOT_DIR)/docker-compose.state-store.yml
HOST_DATABASE_URL ?= postgresql://edim:edim@127.0.0.1:5432/edim

help: ## Show this help
	@echo "edim-dde-api — make targets"
	@echo ""
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-22s %s\n", $$1, $$2}'
	@echo ""
	@echo "Variables: APP_NAME=$(APP_NAME)  BASE=$(BASE)  EXPECT_STATE_STORE=$(EXPECT_STATE_STORE)  PORT=$(PORT)"
	@echo ""
	@echo "Host API + Docker Postgres (az login on laptop works):"
	@echo "  az login"
	@echo "  make host-run          # pg-up + uvicorn on host (foreground)"
	@echo "  make pg-down           # stop Postgres when done"
	@echo "  (put Foundry/Databricks vars in $(DOMAIN_ENV))"
	@echo ""
	@echo "Full Compose (API + Postgres both in Docker — no host az login into container):"
	@echo "  make compose-up && make e2e-dry && make compose-down"
	@echo ""
	@echo "Databricks Apps: make vendor-wheels && make apps-create … (docs §5)"
	@echo "Local MkDocs guide: make guide-site && make compose-up → http://127.0.0.1:8080/guide/"
	@echo "Windows PowerShell: make vendor-wheels-win"
	@echo ""
	@echo "Do not run compose-up and host-run at the same time (both use port 5432 / edim-postgres)."

vendor-wheels: ## Build ai+domain+api wheels + MkDocs guide-site for Docker
	@if [ -n "$(EDIM_AI_PATH)" ]; then export EDIM_AI_PATH="$(EDIM_AI_PATH)"; fi; \
	if [ -n "$(EDIM_DOMAIN_PATH)" ]; then export EDIM_DOMAIN_PATH="$(EDIM_DOMAIN_PATH)"; fi; \
	PYTHON="$(PYTHON)" ./deploy/scripts/build_vendor_wheels.sh

guide-site: ## Build MkDocs Material site → deploy/docker/guide-site (local /guide only)
	@if [ -n "$(EDIM_DOMAIN_PATH)" ]; then export EDIM_DOMAIN_PATH="$(EDIM_DOMAIN_PATH)"; fi; \
	PYTHON="$(PYTHON)" ./deploy/scripts/build_guide_site.sh

vendor-wheels-win: ## Windows PowerShell wrapper for vendor-wheels (uses Git Bash + .venv python)
	powershell -NoProfile -ExecutionPolicy Bypass -File deploy/scripts/build_vendor_wheels.ps1 -GitBashPath "$(GIT_BASH)" -EdimAiPath "$(EDIM_AI_PATH)" -EdimDomainPath "$(EDIM_DOMAIN_PATH)"

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

pg-up: ## Start Postgres only in Docker (API stays on the host)
	@test -f "$(STATE_COMPOSE)" || (echo "error: missing $(STATE_COMPOSE)" >&2; exit 1)
	docker compose -f "$(STATE_COMPOSE)" up -d postgres
	@$(MAKE) pg-wait
	@echo ""
	@echo "Postgres ready on 127.0.0.1:5432  (user/db/password = edim/edim/edim)"
	@echo "Next: make host-run   # or export EDIM_STATE_STORE=postgres and uvicorn yourself"
	@echo "Stop:  make pg-down"

pg-wait: ## Wait until Docker Postgres accepts connections
	@echo "Waiting for Postgres…"
	@bash -c 'set -euo pipefail; \
	deadline=$$((SECONDS+60)); \
	while ! docker compose -f "$(STATE_COMPOSE)" exec -T postgres pg_isready -U edim -d edim >/dev/null 2>&1; do \
	  if (( SECONDS >= deadline )); then echo "error: Postgres not ready within 60s" >&2; exit 1; fi; \
	  sleep 1; \
	done'

pg-down: ## Stop Postgres-only Compose (keeps volume)
	docker compose -f "$(STATE_COMPOSE)" down

pg-ps: ## Show Postgres-only Compose status
	docker compose -f "$(STATE_COMPOSE)" ps

host-run: pg-up ## Postgres in Docker + uvicorn on laptop (uses host az login)
	@echo ""
	@echo "Starting API on host → $(BASE)  (state_store=postgres @ $(HOST_DATABASE_URL))"
	@echo "Ctrl+C stops uvicorn only; Postgres keeps running (make pg-down to stop it)."
	@echo ""
	@bash -c 'set -a; \
	if [ -f "$(DOMAIN_ENV)" ]; then . "$(DOMAIN_ENV)"; fi; \
	set +a; \
	export EDIM_STATE_STORE=postgres; \
	export EDIM_DATABASE_URL="$(HOST_DATABASE_URL)"; \
	if [ -z "$${EDIM_RECOMMENDATION_STORE:-}" ]; then export EDIM_RECOMMENDATION_STORE=postgres; fi; \
	reload_flag=""; \
	if [ "$(RELOAD)" = "1" ]; then reload_flag="--reload"; fi; \
	exec $(PYTHON) -m uvicorn edim_dde_api.main:app --host 127.0.0.1 --port "$(PORT)" $$reload_flag'

host-up: host-run ## Alias for host-run

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
