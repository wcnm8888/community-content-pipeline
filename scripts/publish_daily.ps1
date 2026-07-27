<#
.SYNOPSIS
Automates daily article publishing preparation with a persistent publish browser profile.

.EXAMPLES
.\scripts\publish_daily.ps1 -Mode DryRun
.\scripts\publish_daily.ps1 -Platforms zhihu -Mode DryRun
.\scripts\publish_daily.ps1 -Platforms zhihu,bilibili -Mode Draft
.\scripts\publish_daily.ps1 -Mode Publish

.NOTES
DryRun reads fields, opens platform pages with the publish profile, and checks login/entry state.
Draft fills fields and attempts to save drafts only. It does not click final publish.
Publish runs the Draft path first, then requires typing YES per platform before any final publish click.

Default covers are read from out\YYYY-MM-DD\16-9.png and out\YYYY-MM-DD\3-4.png.

First-time browser profile setup, if you prefer doing it manually:
New-Item -ItemType Directory -Force "E:\社区账号\browser-profiles\publish"
playwright-cli -s=publish open --browser=chrome --profile="E:\社区账号\browser-profiles\publish"

Never run: playwright-cli -s=publish delete-data
#>

param(
    [ValidateSet("DryRun", "Draft", "Publish")]
    [string]$Mode = "DryRun",

    [string[]]$Platforms = @("zhihu", "juejin", "bilibili", "csdn", "douyin", "xiaohongshu"),

    [string]$Cover16x9 = "",

    [string]$Cover3x4 = ""
)

Set-StrictMode -Version 3.0
$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

. (Join-Path $PSScriptRoot "publish\common.ps1")
. (Join-Path $PSScriptRoot "publish\platforms\zhihu.ps1")
. (Join-Path $PSScriptRoot "publish\platforms\juejin.ps1")
. (Join-Path $PSScriptRoot "publish\platforms\bilibili.ps1")
. (Join-Path $PSScriptRoot "publish\platforms\csdn.ps1")
. (Join-Path $PSScriptRoot "publish\platforms\douyin.ps1")
. (Join-Path $PSScriptRoot "publish\platforms\xiaohongshu.ps1")

function Resolve-RequestedPlatforms {
    param([string[]]$Requested)

    $items = New-Object System.Collections.Generic.List[string]
    foreach ($entry in $Requested) {
        foreach ($part in ($entry -split ",")) {
            $value = $part.Trim().ToLowerInvariant()
            if ($value) {
                $items.Add($value) | Out-Null
            }
        }
    }

    if ($items.Count -eq 0 -or ($items -contains "all")) {
        return $script:PublishSupportedPlatforms
    }

    $invalid = @($items | Where-Object { $script:PublishSupportedPlatforms -notcontains $_ })
    if ($invalid.Count -gt 0) {
        throw "Unsupported platform(s): $($invalid -join ', '). Supported: $($script:PublishSupportedPlatforms -join ', ')"
    }

    return @($items | Select-Object -Unique)
}

function Invoke-PlatformByKey {
    param(
        [Parameter(Mandatory = $true)][string]$Platform,
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)]$Pack
    )

    switch ($Platform) {
        "zhihu" { Invoke-ZhihuPublish $Context $Pack; break }
        "juejin" { Invoke-JuejinPublish $Context $Pack; break }
        "bilibili" { Invoke-BilibiliPublish $Context $Pack; break }
        "csdn" { Invoke-CsdnPublish $Context $Pack; break }
        "douyin" { Invoke-DouyinPublish $Context $Pack; break }
        "xiaohongshu" { Invoke-XiaohongshuPublish $Context $Pack; break }
        default { throw "Unsupported platform: $Platform" }
    }
}

$context = New-PublishContext -Root $root -Mode $Mode -Cover16x9 $Cover16x9 -Cover3x4 $Cover3x4
$requestedPlatforms = Resolve-RequestedPlatforms $Platforms
Save-DryRunRecord $context

Write-PublishLog $context "Mode: $Mode"
Write-PublishLog $context ("Platforms: " + ($requestedPlatforms -join ", "))
Write-PublishLog $context "Logs: $($context.LogDir)"

if ($Mode -eq "Publish") {
    Write-PublishLog $context "Publish mode is enabled. Each platform still requires typing YES before final publish." "WARN"
}

if ($Mode -ne "DryRun") {
    Assert-HumanReviewApproved $context
    Assert-PlatformReviewApproved $context $requestedPlatforms
}

Ensure-PublishBrowser $context
$pack = Get-PlatformPack $context

foreach ($platform in $requestedPlatforms) {
    try {
        Invoke-PlatformByKey -Platform $platform -Context $context -Pack $pack
    } catch {
        Write-PublishLog $context "Platform failed: $platform. $($_.Exception.Message)" "ERROR"
        Write-DryRunPlatformResult $context $platform "failed" $null @() @() $_.Exception.Message
        Wait-ManualAction $context "platform $platform failed; inspect browser/logs, then press Enter to continue to the next platform"
    } finally {
        $context.CurrentPlatform = ""
    }
}

Save-DryRunRecord $context
Write-PublishLog $context "Done. No final publish occurs in DryRun or Draft mode."
