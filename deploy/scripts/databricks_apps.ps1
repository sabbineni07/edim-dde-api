param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("sync", "deploy")]
    [string]$Action,

    [Parameter(Mandatory = $true)]
    [string]$WsSource,

    [string]$AppName = "edim-dde-api-dev"
)

$ErrorActionPreference = "Stop"

function Normalize-DatabricksWorkspacePath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $normalized = $Path.Trim().Replace('\', '/')
    if ($normalized -match '(?i)Git/Workspace/(.+)$') {
        return "/Workspace/$($matches[1])"
    }
    if (-not $normalized.StartsWith('/')) {
        throw @"
WS_SOURCE must be a Databricks workspace path starting with '/' (e.g. /Workspace/Users/you/apps/edim-dde-api-dev).
Got: $Path

Git Bash often rewrites /Workspace/... before make sees it. This script unmangles that automatically when possible.
If you still see this error, run make from PowerShell or pass WS_SOURCE with a leading '//' in Git Bash:
  make apps-sync WS_SOURCE=//Workspace/Users/you/apps/edim-dde-api-dev
"@
    }
    return $normalized
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$apiRoot = (Resolve-Path (Join-Path $scriptDir "../..")).Path
Set-Location $apiRoot

$wsPath = Normalize-DatabricksWorkspacePath -Path $WsSource

switch ($Action) {
    "sync" {
        $bundle = Join-Path $apiRoot "deploy/databricks-app"
        $req = Join-Path $bundle "requirements.vendor.txt"
        if (-not (Test-Path $req)) {
            throw "Missing $req - run 'make vendor-wheels' or 'make vendor-wheels-win' first."
        }
        Write-Host "Syncing $bundle -> $wsPath"
        $guideIndex = Join-Path $bundle "guide-site\index.html"
        if (-not (Test-Path $guideIndex)) {
            Write-Warning "guide-site/index.html missing under deploy/databricks-app - /guide will 404 on the App until you run: make guide-site && make copy-guide-site"
        }
        & databricks workspace import-dir $bundle $wsPath --overwrite
    }
    "deploy" {
        Write-Host "Deploying app $AppName from $wsPath"
        & databricks apps deploy $AppName --source-code-path $wsPath --mode SNAPSHOT
        if ($LASTEXITCODE -ne 0) {
            throw "databricks apps deploy failed with exit code $LASTEXITCODE"
        }

        Write-Host "Stopping app $AppName (reload wheels / guide-site after deploy)"
        & databricks apps stop $AppName
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "databricks apps stop returned $LASTEXITCODE (app may already be stopped)"
        }

        Write-Host "Starting app $AppName"
        & databricks apps start $AppName
        if ($LASTEXITCODE -ne 0) {
            throw "databricks apps start failed with exit code $LASTEXITCODE"
        }
    }
}

if ($Action -eq "sync" -and $LASTEXITCODE -ne 0) {
    throw "databricks sync failed with exit code $LASTEXITCODE"
}
