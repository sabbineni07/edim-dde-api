# Build MkDocs Material site -> edim-dde-api/deploy/docker/guide-site
# PowerShell only (do not paste bash from build_guide_site.sh into this file).
#
# Usage (from edim-dde-api):
#   powershell -NoProfile -ExecutionPolicy Bypass -File deploy/scripts/build_guide_site.ps1
#   make guide-site-win
#Requires -Version 5.1
param(
    [string]$EdimDomainPath = "",
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"

function Resolve-PythonExe {
    param(
        [string]$ApiRoot,
        [string]$Override
    )

    if (-not [string]::IsNullOrWhiteSpace($Override)) {
        if (Test-Path $Override) {
            return (Resolve-Path $Override).Path
        }
        $cmd = Get-Command $Override -ErrorAction SilentlyContinue
        if ($cmd) {
            return $cmd.Source
        }
        throw "Python not found at or on PATH: '$Override'"
    }

    if (-not [string]::IsNullOrWhiteSpace($env:PYTHON) -and (Test-Path $env:PYTHON)) {
        return (Resolve-Path $env:PYTHON).Path
    }

    $venvPython = Join-Path $ApiRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return (Resolve-Path $venvPython).Path
    }

    foreach ($candidate in @("py", "python", "python3")) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd) {
            return $cmd.Source
        }
    }

    throw "No Python found. Create .venv in edim-dde-api or set PYTHON to your python.exe path."
}

function Resolve-EdimDomainPath {
    param(
        [string]$ApiRoot,
        [string]$Override
    )

    if (-not [string]::IsNullOrWhiteSpace($Override)) {
        $domain = (Resolve-Path $Override).Path
        if (-not (Test-Path (Join-Path $domain "mkdocs.yml"))) {
            throw "missing mkdocs.yml at '$domain' (check -EdimDomainPath)"
        }
        return $domain
    }

    if (-not [string]::IsNullOrWhiteSpace($env:EDIM_DOMAIN_PATH)) {
        $domain = $env:EDIM_DOMAIN_PATH
        if (Test-Path (Join-Path $domain "mkdocs.yml")) {
            return (Resolve-Path $domain).Path
        }
    }

    $parent = Split-Path $ApiRoot -Parent
    foreach ($name in @("edim-dde-domain", "edim_dde_domain")) {
        $candidate = Join-Path $parent $name
        if (Test-Path (Join-Path $candidate "mkdocs.yml")) {
            return (Resolve-Path $candidate).Path
        }
    }

    throw @"
Could not find edim-dde-domain/mkdocs.yml next to edim-dde-api.
Set EDIM_DOMAIN_PATH or pass -EdimDomainPath, for example:
  make guide-site-win EDIM_DOMAIN_PATH=C:/Code/dim/edim_ai/edim-dde-domain
"@
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$apiRoot = (Resolve-Path (Join-Path $scriptDir "../..")).Path
Set-Location $apiRoot

$Python = Resolve-PythonExe -ApiRoot $apiRoot -Override $Python
$EdimDomainPath = Resolve-EdimDomainPath -ApiRoot $apiRoot -Override $EdimDomainPath
$out = Join-Path $apiRoot "deploy\docker\guide-site"

Write-Host "==> python: $Python"
Write-Host "==> domain: $EdimDomainPath"
Write-Host "==> pip install mkdocs-material (MkDocs 1.x; do not use MkDocs 2)"
& $Python -m pip install -q "mkdocs>=1.6,<2" "mkdocs-material>=9.5,<10"
if ($LASTEXITCODE -ne 0) {
    throw "pip install mkdocs-material failed (exit $LASTEXITCODE)"
}

if (Test-Path $out) {
    Remove-Item -Recurse -Force $out
}
New-Item -ItemType Directory -Force -Path $out | Out-Null
$outAbs = (Resolve-Path $out).Path

Write-Host "==> mkdocs build -> $outAbs"
Push-Location $EdimDomainPath
try {
    & $Python -m mkdocs build --clean -f mkdocs.yml -d $outAbs
    if ($LASTEXITCODE -ne 0) {
        throw "mkdocs build failed (exit $LASTEXITCODE)"
    }
}
finally {
    Pop-Location
}

$index = Join-Path $outAbs "index.html"
if (-not (Test-Path $index)) {
    throw "mkdocs did not produce index.html under $outAbs"
}

$pageCount = (Get-ChildItem -Path $outAbs -Filter "index.html" -Recurse -File).Count
Write-Host "Guide site ready: $outAbs"
Write-Host "  pages: $pageCount index.html files"
Write-Host "  Apps bundle: make copy-guide-site"
Write-Host "  local Docker:  http://127.0.0.1:8080/guide/"
