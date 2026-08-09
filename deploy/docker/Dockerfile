# syntax=docker/dockerfile:1
# Portable image for Azure Container Apps / AKS / App Service / local Docker Compose.
# Same entrypoint as Databricks Apps: edim_dde_api.main:app
#
# Build (from edim-dde-api/ after vendor wheels + guide-site exist):
#   make vendor-wheels   # wheels + MkDocs guide-site
#   docker build -f deploy/docker/Dockerfile -t edim-dde-api:local .
#   # or: make compose-up
#
# Run (single container):
#   docker run --rm -p 8080:8080 --env-file ../edim-dde-domain/.env edim-dde-api:local

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

COPY deploy/docker/requirements.txt /tmp/requirements.txt
COPY deploy/databricks-app/vendor /app/vendor
# Local Docker MkDocs Material site only (not part of Databricks Apps bundle)
COPY deploy/docker/guide-site /app/guide-site

RUN pip install --no-cache-dir -U pip \
 && pip install --no-cache-dir -r /tmp/requirements.txt \
 && pip install --no-cache-dir /app/vendor/*.whl \
 && pip install --no-cache-dir \
      "databricks-sql-connector>=3.0" \
      "azure-identity>=1.15" \
      "azure-keyvault-secrets>=4.8" \
      "openai>=1.40" \
      "psycopg[binary]>=3.1"

ENV EDIM_GUIDE_SITE_DIR=/app/guide-site

# Non-root where possible
RUN useradd --create-home --shell /bin/bash edim && chown -R edim:edim /app
USER edim

EXPOSE 8080

# Azure Container Apps / generic: honor PORT
CMD ["sh", "-c", "uvicorn edim_dde_api.main:app --host 0.0.0.0 --port ${PORT}"]
