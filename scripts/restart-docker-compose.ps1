param(
    [string]$ComposeFile = "docker-compose.yml",
    [string]$ProjectDirectory = (Resolve-Path "$PSScriptRoot\..").Path,
    [switch]$NoBuild,
    [switch]$Pull
)

$ErrorActionPreference = "Stop"

Set-Location $ProjectDirectory

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found. Please install Docker Desktop and make sure docker is available in PATH."
}

if (-not (Test-Path -LiteralPath $ComposeFile)) {
    throw "Compose file not found: $ComposeFile"
}

$composeArgs = @("compose", "-f", $ComposeFile)

if ($Pull) {
    & docker @composeArgs pull
}

$upArgs = @("up", "-d")
if (-not $NoBuild) {
    $upArgs += "--build"
}

& docker @composeArgs @upArgs
& docker @composeArgs ps
