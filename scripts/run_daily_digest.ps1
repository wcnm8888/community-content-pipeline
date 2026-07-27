$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logPath = Join-Path $logDir "daily-digest-$timestamp.log"
$mutex = New-Object System.Threading.Mutex($false, "Local\ContentPipelineDailyDigest")
$lockAcquired = $false

function Write-RunLog {
  param([string]$Message)
  "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message" | Tee-Object -FilePath $logPath -Append
}

function Invoke-LoggedCommand {
  param(
    [Parameter(Mandatory = $true)][string]$FilePath,
    [Parameter(Mandatory = $false)][string[]]$Arguments = @()
  )
  & $FilePath @Arguments 2>&1 | Tee-Object -FilePath $logPath -Append
  if ($LASTEXITCODE -ne 0) {
    throw "$FilePath exited with code $LASTEXITCODE"
  }
}

Set-Location $root

try {
  $lockAcquired = $mutex.WaitOne(0)
  if (-not $lockAcquired) {
    Write-RunLog "Skipped: another daily digest run is already in progress."
    exit 0
  }

  Write-RunLog "Starting daily digest."
  Invoke-LoggedCommand "powershell.exe" @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ".\scripts\preflight.ps1")
  Invoke-LoggedCommand "powershell.exe" @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ".\scripts\start_worker.ps1")
  Invoke-LoggedCommand "python" @(".\scripts\daily_digest.py", "--top", "8", "--limit-per-feed", "5", "--feed-timeout", "12", "--reader-timeout", "18", "--pool-size", "30")
  Invoke-LoggedCommand "python" @(".\scripts\render_content_pool_html.py")
  Invoke-LoggedCommand "python" @(".\scripts\render_topic_candidates_html.py")
  Invoke-LoggedCommand "python" @(".\scripts\render_draft_html.py")
  Invoke-LoggedCommand "python" @(".\scripts\render_article_review_html.py")
  Invoke-LoggedCommand "python" @(".\scripts\render_platform_pack_html.py")
  Invoke-LoggedCommand "powershell.exe" @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ".\scripts\start_preview_server.ps1")
  Write-RunLog "Daily digest completed successfully."
  exit 0
} catch {
  Write-RunLog "Daily digest failed: $($_.Exception.Message)"
  exit 1
} finally {
  if ($lockAcquired) {
    $mutex.ReleaseMutex()
  }
  $mutex.Dispose()
}
