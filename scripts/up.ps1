# Builds and starts db, api and web with Docker Compose, waits until healthy, and prints the URL.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')

Assert-Docker
Initialize-EnvFile

Write-Host "Building and starting Novo Label Studio (db, api, web)..."
Invoke-Compose up -d --build

$port = Get-HttpsPort
$url = "https://localhost:$port"
Write-Host "Waiting for the API to become healthy..."
if (-not (Wait-Healthy $url)) {
    Invoke-Compose ps
    Fail "The app didn't become healthy in time. See the logs with:  docker compose -f deploy/docker-compose.yml logs api"
}

Write-Host ""
Write-Host "Novo Label Studio is running at $url" -ForegroundColor Green
Write-Host "The certificate is self-signed; your browser will ask you to accept it the first time."
