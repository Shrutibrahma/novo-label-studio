# Wipes the development database and part images, then starts fresh (migration 0001 runs on start).
param([switch]$Force)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')

Assert-Docker
Initialize-EnvFile

if (-not $Force) {
    Write-Host "This deletes ALL data: parts, label names, print history, serials, users and part images." -ForegroundColor Yellow
    $answer = Read-Host "Type RESET to continue"
    if ($answer -ne 'RESET') {
        Write-Host "Cancelled. Nothing was changed."
        exit 0
    }
}

Invoke-Compose down --volumes
Write-Host "Database and images wiped. Starting a fresh stack..."
& (Join-Path $PSScriptRoot 'up.ps1')
