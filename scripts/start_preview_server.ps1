$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$siteDir = Join-Path $root "site"
$port = 8010

if (-not (Test-Path $siteDir)) {
  New-Item -ItemType Directory -Path $siteDir -Force | Out-Null
}

$existing = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($existing) {
  Write-Output "Preview server may already be running at http://localhost:$port/draft-latest.html"
  exit 0
}

Start-Process `
  -FilePath "python" `
  -ArgumentList @("-m", "http.server", "$port", "-d", "$siteDir") `
  -WorkingDirectory $root `
  -WindowStyle Hidden

Write-Output "Preview server started:"
Write-Output "http://localhost:$port/draft-latest.html"
