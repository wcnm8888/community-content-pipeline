param(
  [Parameter(Mandatory = $true)]
  [string]$Topic,

  [string]$Angle = "",

  [string]$Audience = "",

  [int]$TopResults = 8,

  [int]$ReaderTimeout = 18,

  [string[]]$Urls = @()
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logPath = Join-Path $logDir "knowledge-share-$timestamp.log"

Set-Location $root

$argsList = @(
  ".\scripts\knowledge_share.py",
  "--topic", $Topic,
  "--top-results", [string]$TopResults,
  "--reader-timeout", [string]$ReaderTimeout
)

if (-not [string]::IsNullOrWhiteSpace($Angle)) {
  $argsList += @("--angle", $Angle)
}

if (-not [string]::IsNullOrWhiteSpace($Audience)) {
  $argsList += @("--audience", $Audience)
}

if ($Urls.Count -gt 0) {
  $argsList += "--urls"
  foreach ($url in $Urls) {
    if (-not [string]::IsNullOrWhiteSpace($url)) {
      $argsList += $url
    }
  }
}

try {
  "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Starting knowledge share generation" | Out-File -FilePath $logPath -Encoding UTF8
  python @argsList 2>&1 | Tee-Object -FilePath $logPath -Append
  python ".\scripts\render_knowledge_share_html.py" 2>&1 | Tee-Object -FilePath $logPath -Append
  python ".\scripts\render_article_review_html.py" 2>&1 | Tee-Object -FilePath $logPath -Append
  python ".\scripts\render_platform_pack_html.py" 2>&1 | Tee-Object -FilePath $logPath -Append
  "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Done" | Tee-Object -FilePath $logPath -Append
} catch {
  "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ERROR: $($_.Exception.Message)" | Tee-Object -FilePath $logPath -Append
  throw
}
