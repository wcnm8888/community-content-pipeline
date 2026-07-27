$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$port = 8020

function Test-WorkerHealth {
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/health" -TimeoutSec 3
    $health = $response.Content | ConvertFrom-Json
    return [bool]$health.ok
  } catch {
    return $false
  }
}

if (Test-WorkerHealth) {
  Write-Output "Content worker is healthy: http://localhost:$port/health"
  exit 0
}

$existing = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
  throw "Port $port is occupied, but the content worker health check failed. Existing process was not stopped."
}

Start-Process `
  -FilePath "python" `
  -ArgumentList @("scripts\worker_server.py") `
  -WorkingDirectory $root `
  -WindowStyle Hidden

Write-Output "Content worker started:"
Write-Output "http://localhost:$port/health"

for ($attempt = 1; $attempt -le 20; $attempt++) {
  Start-Sleep -Seconds 1
  if (Test-WorkerHealth) {
    Write-Output "Content worker is healthy."
    exit 0
  }
}

throw "Content worker did not become healthy within 20 seconds."
