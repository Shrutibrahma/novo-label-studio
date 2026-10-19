# Sets a new password for a user (for example when the only admin has forgotten theirs).
# Usage:  .\scripts\reset-password.ps1            (asks for the username, default "Novo")
#         .\scripts\reset-password.ps1 -Username Novo
# The password is typed hidden, asked twice, and passed to the server on stdin (never on a command line).
param([string]$Username)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')

Assert-Docker
Initialize-EnvFile

$running = @(& docker compose --project-directory $DeployDir -f $ComposeFile ps --services --filter status=running 2>$null)
if (-not ($running -contains 'api')) {
    Fail "The app isn't running. Start it first with .\scripts\up.ps1"
}

if (-not $Username) {
    $Username = Read-Host "Username [Novo]"
    if (-not $Username) { $Username = 'Novo' }
}

function Read-Secret([string]$Prompt) {
    $secure = Read-Host $Prompt -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

$first = Read-Secret "New password (at least 12 characters)"
if ($first.Length -lt 12) { Fail "Password must be at least 12 characters. Nothing was changed." }
$second = Read-Secret "Type it again"
if ($first -cne $second) { Fail "The two passwords don't match. Nothing was changed." }

# Windows PowerShell pipes text to programs as ASCII by default; send UTF-8 so any character survives.
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
$first | & docker compose --project-directory $DeployDir -f $ComposeFile exec -T api python -m app.reset_password $Username
$code = $LASTEXITCODE
$first = $null; $second = $null
if ($code -ne 0) { Fail "The password was not changed (see the message above)." }
Write-Host "Done. Other devices signed in as $Username have been signed out." -ForegroundColor Green
