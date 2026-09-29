# Shared helpers for the scripts in this folder. Dot-sourced; not meant to be run directly.
$ErrorActionPreference = 'Stop'

$script:RepoRoot = Split-Path -Parent $PSScriptRoot
$script:DeployDir = Join-Path $RepoRoot 'deploy'
$script:ComposeFile = Join-Path $DeployDir 'docker-compose.yml'
$script:EnvFile = Join-Path $DeployDir '.env'

function Update-SessionPath {
    # Tools installed with winget (uv) land on PATH only for new sessions; pick them up now.
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$user;$machine;$env:Path"
}

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

function Assert-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Fail "Docker isn't installed. Install Docker Desktop from https://www.docker.com/products/docker-desktop/ and try again."
    }
    & docker info --format '{{.ServerVersion}}' *> $null
    if ($LASTEXITCODE -ne 0) {
        Fail "Docker isn't running. Start Docker Desktop, wait until it says 'Engine running', then try again."
    }
}

function Assert-Uv {
    Update-SessionPath
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Fail "uv isn't installed. Install it with:  winget install --id astral-sh.uv -e   then open a new PowerShell window."
    }
}

function Assert-Node {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Fail "Node.js isn't installed. Install the LTS release from https://nodejs.org/ and open a new PowerShell window."
    }
}

function Read-EnvFile {
    $values = @{}
    if (Test-Path $EnvFile) {
        foreach ($line in Get-Content $EnvFile) {
            if ($line -match '^\s*([A-Z_][A-Z0-9_]*)=(.*)$') { $values[$Matches[1]] = $Matches[2] }
        }
    }
    return $values
}

function Initialize-EnvFile {
    if (Test-Path $EnvFile) { return }
    $bytes = New-Object byte[] 24
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $password = -join ($bytes | ForEach-Object { $_.ToString('x2') })
    $content = "DB_PASSWORD=$password`nHTTPS_PORT=8443`nHTTP_PORT=8088`nSESSION_TTL_HOURS=12`nPUBLIC_BASE_URL=https://localhost:8443`n"
    [System.IO.File]::WriteAllText($EnvFile, $content, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "Created deploy/.env with a random database password."
}

function Invoke-Compose {
    # A simple function (no param block) so arguments like -d reach docker instead of PowerShell's -Debug.
    & docker compose --project-directory $DeployDir -f $ComposeFile @args
    if ($LASTEXITCODE -ne 0) { Fail "docker compose $($args -join ' ') failed." }
}

function Get-HttpsPort {
    $envValues = Read-EnvFile
    if ($envValues.ContainsKey('HTTPS_PORT')) { return $envValues['HTTPS_PORT'] }
    return '8443'
}

function Wait-Healthy([string]$BaseUrl, [int]$TimeoutSeconds = 240) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $code = & curl.exe -ks -o NUL -w '%{http_code}' "$BaseUrl/api/v1/health" 2>$null
        if ($code -eq '200') { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}
