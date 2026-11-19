# Start the FinAlly container. Usage: scripts\start.ps1 [-Build] [-NoOpen]
param(
    [switch]$Build,
    [switch]$NoOpen
)
$ErrorActionPreference = "Stop"

$Image = "finally"
$Container = "finally"
$Port = if ($env:PORT) { $env:PORT } else { "8000" }
$Url = "http://localhost:$Port"

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "docker is not installed or not on PATH."
    exit 1
}

docker image inspect $Image *> $null
if ($Build -or $LASTEXITCODE -ne 0) {
    Write-Host "Building Docker image '$Image'..."
    docker build -t $Image .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

docker container inspect $Container *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Removing existing container '$Container'..."
    docker rm -f $Container | Out-Null
}

New-Item -ItemType Directory -Force -Path (Join-Path $RootDir "db") | Out-Null

$RunArgs = @("run", "-d", "--name", $Container, "-v", "${PWD}\db:/app/db", "-p", "${Port}:8000")
if (Test-Path (Join-Path $RootDir ".env")) {
    $RunArgs += @("--env-file", (Join-Path $RootDir ".env"))
} else {
    Write-Host "Note: no .env file found; starting without it (AI chat will be unconfigured)."
}
$RunArgs += $Image

docker @RunArgs | Out-Null
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "FinAlly is running at $Url"

if (-not $NoOpen) {
    Start-Process $Url
}
