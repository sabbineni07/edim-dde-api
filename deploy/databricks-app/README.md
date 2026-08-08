# Databricks Apps — EDIM DDE API

Thin host adapter for **Databricks Apps**. Runtime code lives in the Python packages;
this folder only defines how the platform starts the process and which deps to install.

**Engineer guide (full design + ACA/Docker):**  
[`edim-dde-domain/docs/api/deploy-and-hosting.md`](../../edim-dde-domain/docs/api/deploy-and-hosting.md)

## Quick start

1. Build installable wheels into `vendor/` (from repo root / siblings):

   ```bash
   # from edim-dde-api/
   ./deploy/scripts/build_vendor_wheels.sh
   ```

2. Set env in `app.yaml` (or Apps UI → Environment) — never commit secrets.

3. Create / deploy the App in the Databricks workspace pointing at this directory
   (or a sync of it). See the engineer guide for CLI/UI steps.

4. Validate: `GET /health`, then live `POST /api/v1/recommendations` while signed into the App
   (SQL uses `X-Forwarded-Access-Token`).
