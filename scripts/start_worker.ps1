$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$port = 8020

$existing = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($existing) {
  Write-Output "Content worker may already be running at http://localhost:$port/health"
  exit 0
}

Start-Process `
  -FilePath "python" `
  -ArgumentList @("scripts\worker_server.py") `
  -WorkingDirectory $root `
  -WindowStyle Hidden

Write-Output "Content worker started:"
Write-Output "http://localhost:$port/health"
