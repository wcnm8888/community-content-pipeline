param(
    [switch]$RequireWorker
)

Set-StrictMode -Version 3.0
$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$requiredFiles = @(
    "config\sources.json",
    "config\platforms.json",
    "prompts\daily-tech-intel.md",
    "prompts\platform-pack.md",
    ".env"
)

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python was not found in PATH."
}

foreach ($relativePath in $requiredFiles) {
    $path = Join-Path $root $relativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required file is missing: $relativePath"
    }
}

$envPath = Join-Path $root ".env"
$envNames = @{}
foreach ($line in (Get-Content -LiteralPath $envPath -Encoding UTF8)) {
    if ($line -match "^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$") {
        $envNames[$Matches[1]] = -not [string]::IsNullOrWhiteSpace($Matches[2])
    }
}

if (-not $envNames.ContainsKey("DEEPSEEK_API_KEY") -or -not $envNames["DEEPSEEK_API_KEY"]) {
    throw "DEEPSEEK_API_KEY is missing in .env. The key value was not displayed."
}

if ($RequireWorker) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8020/health" -TimeoutSec 5
        $health = $response.Content | ConvertFrom-Json
        if (-not $health.ok) {
            throw "Worker health response is not ok."
        }
    } catch {
        throw "Content worker is not healthy at http://127.0.0.1:8020/health."
    }
}

Write-Output "Preflight passed: Python, required files, and required credential names are available."
if ($RequireWorker) {
    Write-Output "Preflight passed: content worker is healthy on port 8020."
}
