# sync_to_cloud.ps1
#
# Runs the local scraper (heavy compute stays on this machine, per the
# local-compute + cloud-serve architecture in Oracle_VPS_Setup.md) and then
# pushes the freshly-updated SQLite database up to the cloud-hosted read-only
# app via scp (OpenSSH client, included by default on Windows 10/11).
#
# Configure via environment variables (set them once in your PowerShell
# profile, or pass them inline before running this script):
#
#   $env:CLOUD_SSH_HOST     = "203.0.113.10"                 # required - your VPS's public IP or hostname
#   $env:CLOUD_SSH_USER     = "ubuntu"                        # optional - defaults to "ubuntu"
#   $env:CLOUD_SSH_KEY      = "$HOME\.ssh\id_ed25519"         # optional - path to your private key
#   $env:CLOUD_REMOTE_PATH  = "/opt/aggregate_apparel/apparel_aggregator.db"  # optional - defaults shown
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

# ---- 1. Validate configuration ----
$RemoteHost = $env:CLOUD_SSH_HOST
if (-not $RemoteHost) {
    Fail "CLOUD_SSH_HOST is not set. Example: `$env:CLOUD_SSH_HOST = '203.0.113.10'"
}
$RemoteUser = if ($env:CLOUD_SSH_USER) { $env:CLOUD_SSH_USER } else { "ubuntu" }
$RemotePath = if ($env:CLOUD_REMOTE_PATH) { $env:CLOUD_REMOTE_PATH } else { "/opt/aggregate_apparel/apparel_aggregator.db" }
$SshKey = $env:CLOUD_SSH_KEY
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
