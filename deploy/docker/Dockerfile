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

FROM prod.artifactory.nfcu.net/docker/python:3.11-slim-bookworm

WORKDIR /app

ARG PIP_INDEX_URL=https://prod.artifactory.nfcu.net/artifactory/api/pypi/pypi/simple
ARG PIP_TRUSTED_HOST=prod.artifactory.nfcu.net
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST} \
    HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY} \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

COPY certs/nfcu-root-ca-r3.crt /tmp/nfcu-root-ca-r3.crt

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && cp /tmp/nfcu-root-ca-r3.crt /usr/local/share/ca-certificates/nfcu-root-ca-r3.crt \
 && update-ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY deploy/docker/requirements.txt /tmp/requirements.txt
COPY deploy/databricks-app/vendor /app/vendor
# Local Docker MkDocs Material site only (not part of Databricks Apps bundle)
COPY deploy/docker/guide-site /app/guide-site

RUN pip install --no-cache-dir -U pip \
 && pip install --no-cache-dir -r /tmp/requirements.txt \
 && pip install --no-cache-dir /app/vendor/*.whl

ENV EDIM_GUIDE_SITE_DIR=/app/guide-site

# Non-root where possible
RUN useradd --create-home --shell /bin/bash edim && chown -R edim:edim /app
USER edim

EXPOSE 8080

# Azure Container Apps / generic: honor PORT
CMD ["sh", "-c", "uvicorn edim_dde_api.main:app --host 0.0.0.0 --port ${PORT}"]
