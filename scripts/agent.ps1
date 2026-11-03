# Starts the Smart Labels print agent on this laptop.
#   scripts/agent.ps1                          simulated printer (default): writes ZPL + PNGs to ./agent-output
#   scripts/agent.ps1 -Mode usb                the real ZQ630 Plus through the Windows print queue
#   scripts/agent.ps1 -Mode usb -Queue ARKSCAN -Language epl   an ARKSCAN 2054A (Seagull "Zebra LP2844" driver)
#   scripts/agent.ps1 -Token <token>           the agent token from setup / Settings -> Printers (saved for next time)
#   scripts/agent.ps1 -ApiBaseUrl https://<server>/api   use a hosted server instead of this laptop (saved too)
#   scripts/agent.ps1 -ApiBaseUrl https://<ip>:8443/api -CaBundle <copy of its labelstudio.crt>   an office-network
#                                              server with a self-signed certificate (deploy/LAN.md; saved too)
# Force the simulated printer's status from another window:  scripts/agent.ps1 -SimStatus out_of_media
param(
    [ValidateSet('simulated', 'usb')][string]$Mode = 'simulated',
    # What the printer understands: zpl (Zebra) or epl (e.g. ARKSCAN 2054A on the 'Zebra LP2844' driver).
    [ValidateSet('zpl', 'epl')][string]$Language = 'zpl',
    [string]$Token,
    [string]$ApiBaseUrl,
    [string]$CaBundle,
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

$saved = @{}
if (Test-Path $agentEnv) {
    foreach ($line in Get-Content $agentEnv) {
        if ($line -match '^\s*(AGENT_TOKEN|API_BASE_URL|AGENT_CA_BUNDLE)=(.+)$') { $saved[$Matches[1]] = $Matches[2].Trim() }
    }
}
if ($CaBundle) {
    if (-not (Test-Path $CaBundle)) { Fail "Certificate not found: $CaBundle" }
    $CaBundle = (Resolve-Path $CaBundle).Path
}
if ($Token -or $ApiBaseUrl -or $CaBundle) {
    # Remember the token and a hosted server's address (e.g. -ApiBaseUrl https://labels.example.com/api).
    if ($Token) { $saved['AGENT_TOKEN'] = $Token }
    if ($ApiBaseUrl) { $saved['API_BASE_URL'] = $ApiBaseUrl }
    if ($CaBundle) { $saved['AGENT_CA_BUNDLE'] = $CaBundle }
    $content = ($saved.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)`n" }) -join ''
    [System.IO.File]::WriteAllText($agentEnv, $content, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "Saved the agent settings to agent/.env."
}
if (-not $Token -and -not $env:AGENT_TOKEN) { $Token = $saved['AGENT_TOKEN'] }
if (-not $ApiBaseUrl -and -not $env:API_BASE_URL) { $ApiBaseUrl = $saved['API_BASE_URL'] }
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
$env:AGENT_PRINTER_LANGUAGE = $Language
$env:AGENT_OUTPUT_DIR = Join-Path $RepoRoot 'agent-output'
if (-not $env:AGENT_POLL_SECONDS) { $env:AGENT_POLL_SECONDS = '1' }
# The self-signed certificate only applies to the local server; a hosted one has a normal public certificate.
$isLocal = ([Uri]$ApiBaseUrl).Host -in @('localhost', '127.0.0.1', 'labels.local')
if ($isLocal -and (Test-Path $cert)) { $env:AGENT_CA_BUNDLE = $cert }
# An office-network server's self-signed certificate, copied to this PC (deploy/LAN.md).
if (-not $CaBundle -and -not $env:AGENT_CA_BUNDLE) { $CaBundle = $saved['AGENT_CA_BUNDLE'] }
if ($CaBundle) { $env:AGENT_CA_BUNDLE = $CaBundle }
if ($HsReadback) { $env:AGENT_HS_READBACK = '1' }  # [SPIKE] ~HS status readback over USB

Write-Host "Starting the print agent ($Mode, $Language) against $ApiBaseUrl. Press Ctrl+C to stop."
if ($Mode -eq 'simulated') { Write-Host "Printed jobs go to $($env:AGENT_OUTPUT_DIR)" }
Push-Location $agentDir
try {
    & uv run --quiet labelstudio-agent run
    exit $LASTEXITCODE
} finally { Pop-Location }
