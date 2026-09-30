# Takes one backup right now (the same as the nightly job): database dump + part images into ./backups.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')

Assert-Docker
Initialize-EnvFile
Invoke-Compose run --rm backup once
Write-Host "Backups are in $(Join-Path $RepoRoot 'backups')" -ForegroundColor Green
