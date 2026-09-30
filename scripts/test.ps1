# Runs every test suite: API (pytest + Testcontainers), agent (pytest), web (typecheck + build) and the
# Playwright end-to-end flows against a throwaway stack with the agent in simulated mode.
param(
    [switch]$SkipE2E,
    [switch]$KeepE2EStack
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')

Assert-Docker
Assert-Uv
Assert-Node
Initialize-EnvFile

$results = [ordered]@{}

# Each suite body returns its exit code (0 = passed).
function Invoke-Suite([string]$Name, [scriptblock]$Body) {
    Write-Host ""
    Write-Host "=== $Name ===" -ForegroundColor Cyan
    $code = 1
    try {
        $code = & $Body | Select-Object -Last 1
    } catch {
        Write-Host $_ -ForegroundColor Red
        $code = 1
    }
    $results[$Name] = if ($code -eq 0) { 'passed' } else { 'FAILED' }
}

# Runs a native command with output shown, returning its exit code (stderr is not treated as an error).
function Run {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $exe = $args[0]
        $rest = @($args | Select-Object -Skip 1)
        & $exe @rest | Out-Host
        return $LASTEXITCODE
    } finally { $ErrorActionPreference = $prev }
}

function Run-Quiet {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $exe = $args[0]
        $rest = @($args | Select-Object -Skip 1)
        & $exe @rest 2>&1 | Out-Null
        return $LASTEXITCODE
    } finally { $ErrorActionPreference = $prev }
}

Invoke-Suite 'API tests' {
    Push-Location (Join-Path $RepoRoot 'api')
    try {
        $c = Run uv sync --frozen --quiet
        if ($c -ne 0) { return $c }
        return (Run uv run pytest -q)
    } finally { Pop-Location }
}

$agentDir = Join-Path $RepoRoot 'agent'
if (Test-Path (Join-Path $agentDir 'pyproject.toml')) {
    Invoke-Suite 'Agent tests' {
        Push-Location $agentDir
        try {
            $c = Run uv sync --frozen --quiet
            if ($c -ne 0) { return $c }
            return (Run uv run pytest -q)
        } finally { Pop-Location }
    }
}

$webDir = Join-Path $RepoRoot 'web'
Invoke-Suite 'Web typecheck + build' {
    Push-Location $webDir
    try {
        if (-not (Test-Path (Join-Path $webDir 'node_modules'))) {
            $c = Run npm ci --no-audit --no-fund
            if ($c -ne 0) { return $c }
        }
        $c = Run npx tsc --noEmit -p .
        if ($c -ne 0) { return $c }
        return (Run npx vite build --logLevel warn)
    } finally { Pop-Location }
}

if (-not $SkipE2E) {
    $e2eOverride = Join-Path $DeployDir 'docker-compose.e2e.yml'
    $compose = @('compose', '--project-directory', $DeployDir, '-p', 'labelstudio-e2e', '-f', $ComposeFile, '-f', $e2eOverride)
    Invoke-Suite 'End-to-end (Playwright)' {
        Run-Quiet docker @compose down --volumes --remove-orphans | Out-Null
        try {
            $c = Run docker @compose up -d --build --quiet-pull
            if ($c -ne 0) { return $c }
            if (-not (Wait-Healthy 'https://localhost:9443')) {
                Write-Host 'The e2e stack did not become healthy.' -ForegroundColor Red
                return 1
            }
            Push-Location $webDir
            try {
                $c = Run npx playwright install chromium
                if ($c -ne 0) { return $c }
                $env:E2E_BASE_URL = 'https://localhost:9443'
                $env:E2E_REPO_ROOT = $RepoRoot
                $e2eOut = Join-Path $RepoRoot 'agent-output\e2e'
                if (Test-Path $e2eOut) { Get-ChildItem $e2eOut -Recurse -File | Remove-Item -Force -ErrorAction SilentlyContinue }
                return (Run npx playwright test)
            } finally { Pop-Location }
        } finally {
            if (-not $KeepE2EStack) { Run-Quiet docker @compose down --volumes --remove-orphans | Out-Null }
        }
    }
}

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
$failed = $false
foreach ($k in $results.Keys) {
    if ($results[$k] -eq 'passed') {
        Write-Host ("{0,-28} {1}" -f $k, $results[$k]) -ForegroundColor Green
    } else {
        Write-Host ("{0,-28} {1}" -f $k, $results[$k]) -ForegroundColor Red
        $failed = $true
    }
}
if ($failed) { exit 1 }
