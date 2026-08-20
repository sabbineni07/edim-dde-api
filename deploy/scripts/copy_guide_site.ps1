# Copy MkDocs output into the Databricks Apps bundle.
# PowerShell only. Do not paste bash into this file.
#Requires -Version 5.1

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$apiRoot = (Resolve-Path (Join-Path $scriptDir "../..")).Path
Set-Location $apiRoot

$src = Join-Path $apiRoot "deploy\docker\guide-site"
$dst = Join-Path $apiRoot "deploy\databricks-app\guide-site"
$index = Join-Path $src "index.html"

if (-not (Test-Path $index)) {
    throw "Run make guide-site-win first. Missing $index"
}

if (Test-Path $dst) {
    Remove-Item -Recurse -Force $dst
}
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item -Path (Join-Path $src "*") -Destination $dst -Recurse -Force

$copied = Join-Path $dst "index.html"
if (-not (Test-Path $copied)) {
    throw "Copy failed: missing $copied"
}

$pageCount = (Get-ChildItem -Path $dst -Filter "index.html" -Recurse -File).Count
Write-Host "Copied guide site -> $dst ($pageCount index.html files)"
