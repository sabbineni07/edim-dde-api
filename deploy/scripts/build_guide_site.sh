#!/usr/bin/env bash
# Build MkDocs Material site into edim-dde-api/deploy/docker/guide-site/
# for local Docker /guide only (not Databricks Apps).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"          # edim-dde-api
PARENT="$(cd "$ROOT/.." && pwd)"
DOMAIN="${EDIM_DOMAIN_PATH:-$PARENT/edim-dde-domain}"
OUT="$ROOT/deploy/docker/guide-site"

# Absolutize PYTHON before any cd (relative .venv/bin/python breaks after cd domain)
_py_raw="${PYTHON:-python3}"
if [[ "$_py_raw" == /* ]]; then
  PYTHON="$_py_raw"
elif [[ -x "$ROOT/$_py_raw" ]]; then
  PYTHON="$ROOT/$_py_raw"
elif command -v "$_py_raw" >/dev/null 2>&1; then
  PYTHON="$(command -v "$_py_raw")"
else
  echo "error: cannot resolve PYTHON=$_py_raw" >&2
  exit 1
fi

if [[ ! -f "$DOMAIN/mkdocs.yml" ]]; then
  echo "error: missing $DOMAIN/mkdocs.yml" >&2
  exit 1
fi

echo "==> installing mkdocs-material into: $PYTHON"
"$PYTHON" -m pip install -q "mkdocs-material>=9.5"

echo "==> mkdocs build → $OUT"
rm -rf "$OUT"
mkdir -p "$OUT"
(
  cd "$DOMAIN"
  "$PYTHON" -m mkdocs build --clean -f mkdocs.yml -d "$OUT"
)

# Ensure directory URLs resolve under FastAPI StaticFiles(html=True)
if [[ -f "$OUT/index.html" ]]; then
  echo "Guide site ready: $OUT"
  echo "  pages: $(find "$OUT" -name 'index.html' | wc -l | tr -d ' ') index.html files"
  echo "  open after compose-up: http://127.0.0.1:8080/guide/"
else
  echo "error: mkdocs did not produce index.html" >&2
  exit 1
fi
