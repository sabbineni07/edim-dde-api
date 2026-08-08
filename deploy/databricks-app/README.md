# Databricks Apps — EDIM DDE API (FastAPI)

Thin host adapter. **Runtime** = FastAPI via `app.yaml` → `uvicorn`.  
**Control plane** to create/deploy = Databricks Apps console or CLI (not a frontend UI app).

**Engineer guide:**  
[`edim-dde-domain/docs/api/deploy-and-hosting.md`](../../../edim-dde-domain/docs/api/deploy-and-hosting.md) §5  
(packaging Options A–D, naming `edim-dde-api-*`)  
**Key Vault Secrets User for App SP:**  
[`key-vault-bootstrap.md`](../../../edim-dde-domain/docs/platform/key-vault-bootstrap.md) §7

## Quick start (Option A — bundle + vendor wheels)

```bash
cd edim-dde-api
make help
make vendor-wheels
# edit deploy/databricks-app/app.yaml  (REPLACE_* — no secrets in git)
make apps-create APP_NAME=edim-dde-api-dev
# Grant App SP → Key Vault Secrets User (guide §7)
make apps-sync  APP_NAME=edim-dde-api-dev WS_SOURCE=/Workspace/Users/<you>/apps/edim-dde-api-dev
make apps-deploy APP_NAME=edim-dde-api-dev WS_SOURCE=/Workspace/Users/<you>/apps/edim-dde-api-dev
curl -sS "https://<app-url>/health"
```

What is installed: `vendor/*.whl` listed in `requirements.vendor.txt` — **not** package `src/` trees.  
`vendor/` is gitignored; rebuild before each deploy (or move to a private index — Option C in the guide).

Validate live SQL while signed into the App (`X-Forwarded-Access-Token`). See guide §5.7.
