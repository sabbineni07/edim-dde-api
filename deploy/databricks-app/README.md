# Databricks Apps — EDIM DDE API (FastAPI)

Thin host adapter. **Runtime** = FastAPI via `app.yaml` → `uvicorn`.  
**Control plane** to create/deploy = Databricks Apps console or CLI (not a frontend UI app).

**Engineer guide:**  
[`edim-dde-domain/docs/api/deploy-and-hosting.md`](../../../edim-dde-domain/docs/api/deploy-and-hosting.md) §5  
(packaging Options A–D, naming `edim-dde-api-*`)  
**Key Vault Secrets User for App SP:**  
[`key-vault-bootstrap.md`](../../../edim-dde-domain/docs/platform/key-vault-bootstrap.md) §7

The MkDocs Material **`/guide`** site is **local Docker by default**. To mount it **temporarily on this App**:

1. `make guide-site` from `edim-dde-api` (Windows: uses `deploy/scripts/build_guide_site.ps1`; or run that `.ps1` directly).
2. Copy `deploy/docker/guide-site` → `deploy/databricks-app/guide-site` (must contain `index.html`).
3. Set App env **`EDIM_MOUNT_GUIDE=1`** (uncomment in `app.yaml` or Apps → Environment).
4. `make apps-sync` + `make apps-deploy`. Open `https://<app-url>/guide/`.

Remove `guide-site/` and the env var when you no longer need it. Do not commit the generated HTML.

Default without the env var: `/guide` is not mounted (`DATABRICKS_APP_PORT`). Docker: `make guide-site && make compose-up` → `http://127.0.0.1:8080/guide/`.

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

**Windows / Git Bash:** `make apps-sync` and `make apps-deploy` use `deploy/scripts/databricks_apps.ps1`, which fixes paths like `C:/Program Files/Git/Workspace/...` → `/Workspace/...`. If sync still fails, run from **PowerShell**, or use `WS_SOURCE=//Workspace/Users/...` in Git Bash.

What is installed: `vendor/*.whl` listed in `requirements.vendor.txt` — **not** package `src/` trees.  
`vendor/` is gitignored; rebuild before each deploy (or move to a private index — Option C in the guide).

Validate live SQL while signed into the App (`X-Forwarded-Access-Token`). See guide §5.7.
