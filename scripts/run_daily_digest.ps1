$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logPath = Join-Path $logDir "daily-digest-$timestamp.log"

Set-Location $root

try {
  "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Starting daily digest" | Out-File -FilePath $logPath -Encoding UTF8
  python ".\scripts\daily_digest.py" --top 8 --limit-per-feed 5 --feed-timeout 12 --reader-timeout 18 --pool-size 30 2>&1 | Tee-Object -FilePath $logPath -Append
  python ".\scripts\render_content_pool_html.py" 2>&1 | Tee-Object -FilePath $logPath -Append
  python ".\scripts\render_topic_candidates_html.py" 2>&1 | Tee-Object -FilePath $logPath -Append
  python ".\scripts\render_draft_html.py" 2>&1 | Tee-Object -FilePath $logPath -Append
  python ".\scripts\render_article_review_html.py" 2>&1 | Tee-Object -FilePath $logPath -Append
  python ".\scripts\render_platform_pack_html.py" 2>&1 | Tee-Object -FilePath $logPath -Append
  & ".\scripts\start_preview_server.ps1" 2>&1 | Tee-Object -FilePath $logPath -Append
  "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Done" | Tee-Object -FilePath $logPath -Append
} catch {
  "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ERROR: $($_.Exception.Message)" | Tee-Object -FilePath $logPath -Append
  throw
}
