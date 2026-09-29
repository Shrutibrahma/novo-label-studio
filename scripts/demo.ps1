# Loads about 50 sample parts (including NP-10421 with the label name "10-32 x 1/2 16") into the running
# stack. Safe to run more than once. Requires scripts/up.ps1 and first-run setup in the browser.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')

Assert-Docker
Initialize-EnvFile

$running = & docker compose --project-directory $DeployDir -f $ComposeFile ps --status running --services 2>$null
if (-not ($running -contains 'api')) {
    Fail "The app isn't running. Start it first with scripts/up.ps1."
}

Invoke-Compose exec -T api python -m app.demo
