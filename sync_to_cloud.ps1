# sync_to_cloud.ps1
#
# Runs the local scraper (heavy compute stays on this machine, per the
# local-compute + cloud-serve architecture in Oracle_VPS_Setup.md) and then
# pushes the freshly-updated SQLite database up to the cloud-hosted read-only
# app via scp (OpenSSH client, included by default on Windows 10/11).
#
# Defaults below are already set to this project's actual VPS (see
# MAINTENANCE.md) - running `.\sync_to_cloud.ps1` with no configuration just
# works. Override any of them via environment variable only if you ever need
# to point this at a different host (set them once in your PowerShell
# profile, or inline before running this script):
#
#   $env:CLOUD_SSH_HOST     = "203.0.113.10"                 # overrides the default VPS IP below
#   $env:CLOUD_SSH_USER     = "ubuntu"                        # overrides the default user below
#   $env:CLOUD_SSH_KEY      = "$HOME\.ssh\id_ed25519"         # overrides the default key path below
#   $env:CLOUD_REMOTE_PATH  = "/opt/aggregate_apparel/apparel_aggregator.db"  # overrides the default remote path below
#   $env:CLOUD_RESTART_SERVICE = "true"                       # optional - restart the remote systemd service after sync
#
# Usage:
#   .\sync_to_cloud.ps1
#   .\sync_to_cloud.ps1 -SkipScrape      # only sync the existing local DB, don't re-scrape first

param(
    [switch]$SkipScrape
)

$ErrorActionPreference = "Stop"

function Fail($message) {
    Write-Error $message
    exit 1
}

# ---- 1. Resolve configuration (hardcoded defaults for this project's VPS,
# overridable via environment variable) ----
$RemoteHost = if ($env:CLOUD_SSH_HOST) { $env:CLOUD_SSH_HOST } else { "REDACTED_VPS_IP" }
$RemoteUser = if ($env:CLOUD_SSH_USER) { $env:CLOUD_SSH_USER } else { "ubuntu" }
$RemotePath = if ($env:CLOUD_REMOTE_PATH) { $env:CLOUD_REMOTE_PATH } else { "/opt/aggregate_apparel/apparel_aggregator.db" }
$SshKey = if ($env:CLOUD_SSH_KEY) { $env:CLOUD_SSH_KEY } else { "$HOME\.ssh\id_ed25519" }
$RestartService = $env:CLOUD_RESTART_SERVICE -eq "true"

$LocalDb = Join-Path $PSScriptRoot "apparel_aggregator.db"

# ---- 2. Run the local scraper + franchise discovery (heavy compute, local only) ----
if (-not $SkipScrape) {
    Write-Host "==> Running scraper.py (scrape + franchise discovery)..." -ForegroundColor Cyan
    Push-Location $PSScriptRoot
    try {
        py scraper.py
        if ($LASTEXITCODE -ne 0) {
            Fail "scraper.py exited with code $LASTEXITCODE. Aborting sync (not pushing a possibly-incomplete database)."
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "==> Skipping scrape (--SkipScrape); syncing existing local database as-is." -ForegroundColor Yellow
}

if (-not (Test-Path $LocalDb)) {
    Fail "Local database not found at $LocalDb. Run scraper.py at least once before syncing."
}

# ---- 3. Push the database up via scp ----
$ScpArgs = @()
if ($SshKey) { $ScpArgs += @("-i", $SshKey) }
$ScpArgs += @($LocalDb, "${RemoteUser}@${RemoteHost}:${RemotePath}")

Write-Host "==> Syncing $LocalDb -> ${RemoteUser}@${RemoteHost}:${RemotePath}" -ForegroundColor Cyan
& scp @ScpArgs
if ($LASTEXITCODE -ne 0) {
    Fail "scp failed with exit code $LASTEXITCODE. Check CLOUD_SSH_HOST/CLOUD_SSH_USER/CLOUD_SSH_KEY and that the remote path's directory exists."
}

# ---- 4. Optionally restart the remote service (usually unnecessary - see Oracle_VPS_Setup.md) ----
if ($RestartService) {
    $SshArgs = @()
    if ($SshKey) { $SshArgs += @("-i", $SshKey) }
    $SshArgs += @("${RemoteUser}@${RemoteHost}", "sudo systemctl restart aggregate-apparel")

    Write-Host "==> Restarting remote aggregate-apparel service..." -ForegroundColor Cyan
    & ssh @SshArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Remote service restart failed (exit code $LASTEXITCODE). The sync itself succeeded; you may need to restart it manually."
    }
}

Write-Host "==> Done. Cloud database is up to date." -ForegroundColor Green
