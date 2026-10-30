# Operations tests (v1.1 U5), run by scripts/test.ps1 with throwaway containers:
#   1. backup copy off this machine: success, and failure on an unwritable folder (the local backup stays)
#   2. Caddy allowed IP ranges: an address outside ALLOWED_CIDRS gets 403; with it empty, requests pass through
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')

$net = "nsl-ops-$PID"
$work = Join-Path ([IO.Path]::GetTempPath()) "nsl-ops-$PID"
$failures = @()
function Check([bool]$ok, [string]$what) {
    if ($ok) { Write-Host "  ok    $what" } else { Write-Host "  FAIL  $what" -ForegroundColor Red; $script:failures += $what }
}
function Invoke-Docker {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & docker.exe @args 2>&1 | ForEach-Object { "$_" } } finally { $ErrorActionPreference = $prev }
}
function DockerPath([string]$p) { $p -replace '\\', '/' }

try {
    New-Item -ItemType Directory -Force (Join-Path $work 'backups'), (Join-Path $work 'copy'), (Join-Path $work 'assets\assets') | Out-Null
    Set-Content -Path (Join-Path $work 'assets\assets\a.png') -Value 'x'
    Invoke-Docker network create $net | Out-Null
    Invoke-Docker run -d --name "$net-db" --network $net --network-alias db -e POSTGRES_USER=label -e POSTGRES_PASSWORD=pw `
        -e POSTGRES_DB=label postgres:16 | Out-Null
    $ready = $false
    foreach ($i in 1..60) {
        Invoke-Docker exec "$net-db" pg_isready -U label -d label | Out-Null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    Check $ready 'test database started'

    $backupSh = DockerPath (Join-Path $DeployDir 'backup.sh')
    function Backup([string]$copyMount) {
        Invoke-Docker run --rm --network $net -e DB_PASSWORD=pw -e BACKUP_COPY_ENABLED=yes `
            -v "${backupSh}:/backup.sh:ro" -v "$(DockerPath (Join-Path $work 'backups')):/backups" `
            -v "$(DockerPath (Join-Path $work 'assets')):/data" -v $copyMount `
            --entrypoint sh postgres:16 /backup.sh once
    }

    Write-Host "Backup copy off this machine"
    $out = Backup "$(DockerPath (Join-Path $work 'copy')):/backup-copy"
    $status = Get-Content (Join-Path $work 'backups\last-backup.json') -Raw | ConvertFrom-Json
    Check ($status.copied -eq $true) 'status says copied'
    Check (@(Get-ChildItem (Join-Path $work 'copy') -Filter 'label-*.dump').Count -eq 1) 'dump copied'
    Check (@(Get-ChildItem (Join-Path $work 'copy') -Filter 'assets-*.tar.gz').Count -eq 1) 'images copied'

    Start-Sleep -Seconds 1  # a new backup stamp
    $out = Backup "$(DockerPath (Join-Path $work 'copy')):/backup-copy:ro"
    $status = Get-Content (Join-Path $work 'backups\last-backup.json') -Raw | ConvertFrom-Json
    Check ($status.copied -eq $false -and $status.copy_error) 'unwritable folder: status says not copied, with the error'
    Check (@(Get-ChildItem (Join-Path $work 'backups') -Filter 'label-*.dump').Count -eq 2) 'local backup kept'
    Check (($out -join "`n") -match 'copy FAILED') 'failure logged'

    Write-Host "Caddy allowed IP ranges"
    $caddyfile = DockerPath (Join-Path $DeployDir 'Caddyfile')
    $caddyStart = DockerPath (Join-Path $DeployDir 'caddy-start.sh')
    function Caddy([string]$cidrs, [int]$port) {
        $name = "$net-caddy-$port"
        Invoke-Docker run -d --name $name --network $net -p "${port}:80" -e "SITE_DOMAIN=http://:80" -e "ALLOWED_CIDRS=$cidrs" `
            -v "${caddyfile}:/etc/caddy/Caddyfile:ro" -v "${caddyStart}:/caddy-start.sh:ro" `
            --entrypoint sh caddy:2.8.4 /caddy-start.sh | Out-Null
        $code = ''
        foreach ($i in 1..30) {
            $code = & curl.exe -s -o NUL -w '%{http_code}' "http://localhost:$port/" 2>$null
            if ($code -and $code -ne '000') { break }
            Start-Sleep -Seconds 1
        }
        return @{ code = $code; logs = (Invoke-Docker logs $name) -join "`n" }
    }
    $denied = Caddy '10.123.0.0/16, 10.124.0.0/16' 18491
    Check ($denied.code -eq '403') "address outside ALLOWED_CIDRS gets 403 (got $($denied.code))"
    $open = Caddy '' 18492
    Check ($open.code -ne '403' -and $open.code -ne '000') "empty ALLOWED_CIDRS passes requests on (got $($open.code))"
    Check ($open.logs -match 'WARNING: ALLOWED_CIDRS is empty') 'empty ALLOWED_CIDRS logs a warning'
} finally {
    foreach ($c in "$net-caddy-18491", "$net-caddy-18492", "$net-db") { Invoke-Docker rm -f $c | Out-Null }
    Invoke-Docker network rm $net | Out-Null
    Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
}

if ($failures.Count) { Write-Host "$($failures.Count) operations check(s) failed" -ForegroundColor Red; exit 1 }
Write-Host "Operations checks passed" -ForegroundColor Green
exit 0
