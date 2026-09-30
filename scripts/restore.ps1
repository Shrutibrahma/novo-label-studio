# Restores a backup made by the nightly job or scripts/backup-now.ps1 (spec section 15, acceptance A12).
#   scripts/restore.ps1                         newest backup in ./backups
#   scripts/restore.ps1 -Stamp 20260929-020000  a specific one
# On a fresh machine: run scripts/up.ps1 once first, then this script.
param(
    [string]$Stamp,
    [switch]$Force
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')

Assert-Docker
Initialize-EnvFile
$backups = Join-Path $RepoRoot 'backups'
if (-not $Stamp) {
    $latest = Get-ChildItem $backups -Filter 'label-*.dump' -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -Last 1
    if (-not $latest) { Fail "No backups found in $backups." }
    $Stamp = $latest.BaseName.Substring(6)
}
$dump = Join-Path $backups "label-$Stamp.dump"
$assets = Join-Path $backups "assets-$Stamp.tar.gz"
if (-not (Test-Path $dump)) { Fail "Missing $dump" }
if (-not (Test-Path $assets)) { Fail "Missing $assets" }

if (-not $Force) {
    Write-Host "This replaces ALL current data with the backup from $Stamp." -ForegroundColor Yellow
    if ((Read-Host "Type RESTORE to continue") -ne 'RESTORE') { Write-Host "Cancelled. Nothing was changed."; exit 0 }
}

Write-Host "Stopping the API and web..."
Invoke-Compose stop api web
Invoke-Compose up -d db
Write-Host "Restoring the database from label-$Stamp.dump..."
Invoke-Compose run --rm --no-deps -e "STAMP=$Stamp" --entrypoint sh backup -c 'PGPASSWORD="$DB_PASSWORD" pg_restore -h db -U label -d label --clean --if-exists --no-owner --exit-on-error "/backups/label-$STAMP.dump"'
Write-Host "Restoring part images from assets-$Stamp.tar.gz..."
Invoke-Compose run --rm --no-deps -e "STAMP=$Stamp" --user root --entrypoint sh backup -c 'find /data/assets -mindepth 1 -delete; tar -xzf "/backups/assets-$STAMP.tar.gz" -C /data && chown -R 10001 /data/assets'
Write-Host "Starting the app..."
& (Join-Path $PSScriptRoot 'up.ps1')
