param(
    [string]$GitBashPath = "C:/Program Files/Git/bin/bash.exe",
    [string]$EdimAiPath = "",
    [string]$EdimDomainPath = ""
)

$ErrorActionPreference = "Stop"

function Convert-ToMsysPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $normalized = $Path.Replace('\\', '/')
    if ($normalized -match '^([A-Za-z]):/(.*)$') {
        $drive = $matches[1].ToLowerInvariant()
        $rest = $matches[2]
        return "/$drive/$rest"
    }
    return $normalized
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$apiRoot = (Resolve-Path (Join-Path $scriptDir "../..")).Path
Set-Location $apiRoot

if (-not (Test-Path $GitBashPath)) {
    throw "Git Bash not found at '$GitBashPath'. Install Git for Windows or pass -GitBashPath."
}

if ([string]::IsNullOrWhiteSpace($env:PYTHON)) {
    $venvPython = Join-Path $apiRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        throw "Expected venv python at '$venvPython'. Activate/create the API venv first."
    }
    $env:PYTHON = Convert-ToMsysPath -Path $venvPython
}

if (-not [string]::IsNullOrWhiteSpace($EdimAiPath)) {
    $env:EDIM_AI_PATH = Convert-ToMsysPath -Path $EdimAiPath
}
if (-not [string]::IsNullOrWhiteSpace($EdimDomainPath)) {
    $env:EDIM_DOMAIN_PATH = Convert-ToMsysPath -Path $EdimDomainPath
}

Write-Host "Using Git Bash: $GitBashPath"
Write-Host "Using PYTHON:   $env:PYTHON"

& $GitBashPath "deploy/scripts/build_vendor_wheels.sh"
if ($LASTEXITCODE -ne 0) {
    throw "build_vendor_wheels.sh failed with exit code $LASTEXITCODE"
}
