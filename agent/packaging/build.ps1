# Builds agent\dist\labelstudio-agent.exe with PyInstaller (spec section 4: packaged with PyInstaller).
$ErrorActionPreference = 'Stop'
$agentDir = Split-Path -Parent $PSScriptRoot
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine') + ";$env:Path"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "uv isn't installed: winget install --id astral-sh.uv -e" }

Push-Location $agentDir
try {
    & uv sync --frozen
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }
    & uv run pyinstaller --noconfirm --clean --onefile --name labelstudio-agent `
        --hidden-import win32timezone --collect-submodules agent `
        --distpath dist --workpath build packaging\entry.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
    Write-Host "Built $agentDir\dist\labelstudio-agent.exe" -ForegroundColor Green
} finally { Pop-Location }
