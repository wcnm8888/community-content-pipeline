$ErrorActionPreference = "Stop"

$taskName = "ContentPipelineDailyDigest"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$scriptPath = Join-Path $root "scripts\run_daily_digest.ps1"

$action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""

$trigger = New-ScheduledTaskTrigger -Daily -At 19:10
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable

Register-ScheduledTask `
  -TaskName $taskName `
  -Action $action `
  -Trigger $trigger `
  -Settings $settings `
  -Description "Generate overseas tech intelligence digest for social-platform drafts." `
  -Force | Out-Null

Write-Output "Registered scheduled task: $taskName"
Write-Output "Daily run time: 19:10"
