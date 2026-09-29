# Stops db, api and web. Data (database, part images) is kept in Docker volumes.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')

Assert-Docker
Initialize-EnvFile
Invoke-Compose down
Write-Host "Stopped. Your data is kept; run scripts/up.ps1 to start again." -ForegroundColor Green
