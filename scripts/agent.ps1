# Starts the Smart Labels print agent on this laptop.
#   scripts/agent.ps1                          simulated printer (default): writes ZPL + PNGs to ./agent-output
#   scripts/agent.ps1 -Mode usb                the real ZQ630 Plus through the Windows print queue
#   scripts/agent.ps1 -Token <token>           the agent token from setup / Settings -> Printers (saved for next time)
# Force the simulated printer's status from another window:  scripts/agent.ps1 -SimStatus out_of_media
param(
    [ValidateSet('simulated', 'usb')][string]$Mode = 'simulated',
    [string]$Token,
    [string]$ApiBaseUrl,
    [string]$Queue = 'ZQ630 Plus',
    [ValidateSet('', 'ready', 'offline', 'out_of_media', 'head_open', 'paused', 'error')][string]$SimStatus = '',
    [switch]$HsReadback
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')

Assert-Uv
$agentDir = Join-Path $RepoRoot 'agent'
$agentEnv = Join-Path $agentDir '.env'

if ($SimStatus) {
    Push-Location $agentDir
    try { & uv run --quiet labelstudio-agent sim-status $SimStatus; exit $LASTEXITCODE } finally { Pop-Location }
}

if ($Token) {
    [System.IO.File]::WriteAllText($agentEnv, "AGENT_TOKEN=$Token`n", (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "Saved the agent token to agent/.env."
} elseif (-not $env:AGENT_TOKEN -and (Test-Path $agentEnv)) {
    foreach ($line in Get-Content $agentEnv) {
        if ($line -match '^\s*AGENT_TOKEN=(.+)$') { $Token = $Matches[1].Trim() }
    }
}
if (-not $Token) { $Token = $env:AGENT_TOKEN }
if (-not $Token) {
    Fail "No agent token. Run:  scripts/agent.ps1 -Token <token>   (the token is shown once in setup step 3, or issue a new one in Settings -> Printers)."
}

if (-not $ApiBaseUrl) { $ApiBaseUrl = if ($env:API_BASE_URL) { $env:API_BASE_URL } else { "https://localhost:$(Get-HttpsPort)/api" } }
$cert = Join-Path $DeployDir 'certs\labelstudio.crt'

$env:AGENT_TOKEN = $Token
$env:API_BASE_URL = $ApiBaseUrl
$env:AGENT_PRINTER_MODE = $Mode
$env:AGENT_PRINTER_QUEUE = $Queue
$env:AGENT_OUTPUT_DIR = Join-Path $RepoRoot 'agent-output'
if (-not $env:AGENT_POLL_SECONDS) { $env:AGENT_POLL_SECONDS = '1' }
if (Test-Path $cert) { $env:AGENT_CA_BUNDLE = $cert }
if ($HsReadback) { $env:AGENT_HS_READBACK = '1' }  # [SPIKE] ~HS status readback over USB

Write-Host "Starting the print agent ($Mode) against $ApiBaseUrl. Press Ctrl+C to stop."
if ($Mode -eq 'simulated') { Write-Host "Printed jobs go to $($env:AGENT_OUTPUT_DIR)" }
Push-Location $agentDir
try {
    & uv run --quiet labelstudio-agent run
    exit $LASTEXITCODE
} finally { Pop-Location }
