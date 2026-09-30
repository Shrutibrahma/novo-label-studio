# Installs the agent as a Windows service with NSSM (spec section 4). Run in an elevated PowerShell on the
# laptop connected to the ZQ630 Plus, after packaging\build.ps1:
#   .\install-service.ps1 -Token <agent token> -ApiBaseUrl https://labels.local/api -Nssm C:\tools\nssm.exe
# NSSM: https://nssm.cc/download (download it yourself; this script doesn't fetch anything).
param(
    [Parameter(Mandatory = $true)][string]$Token,
    [Parameter(Mandatory = $true)][string]$ApiBaseUrl,
    [Parameter(Mandatory = $true)][string]$Nssm,
    [string]$Queue = 'ZQ630 Plus',
    [string]$CaBundle = '',
    [string]$ServiceName = 'LabelStudioAgent',
    [switch]$HsReadback
)
$ErrorActionPreference = 'Stop'

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this script in an elevated (Administrator) PowerShell."
}
if (-not (Test-Path $Nssm)) { throw "nssm.exe not found at $Nssm" }
$exe = Join-Path (Split-Path -Parent $PSScriptRoot) 'dist\labelstudio-agent.exe'
if (-not (Test-Path $exe)) { throw "Build the agent first: packaging\build.ps1" }

$installDir = Join-Path $env:ProgramFiles 'LabelStudio'
New-Item -ItemType Directory -Force $installDir | Out-Null
Copy-Item $exe $installDir -Force
$target = Join-Path $installDir 'labelstudio-agent.exe'

& $Nssm install $ServiceName $target run
& $Nssm set $ServiceName DisplayName "Smart Labels print agent"
& $Nssm set $ServiceName Start SERVICE_AUTO_START
$envs = @("AGENT_TOKEN=$Token", "API_BASE_URL=$ApiBaseUrl", "AGENT_PRINTER_MODE=usb", "AGENT_PRINTER_QUEUE=$Queue",
          "AGENT_POLL_SECONDS=1")
if ($CaBundle) { $envs += "AGENT_CA_BUNDLE=$CaBundle" }
if ($HsReadback) { $envs += "AGENT_HS_READBACK=1" }
& $Nssm set $ServiceName AppEnvironmentExtra @envs
& $Nssm start $ServiceName
Write-Host "Service $ServiceName installed and started. Log: $env:ProgramData\LabelStudio\agent.log" -ForegroundColor Green
