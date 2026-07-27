Set-StrictMode -Version 3.0

$script:PublishSupportedPlatforms = @(
    "zhihu",
    "juejin",
    "bilibili",
    "csdn",
    "douyin",
    "xiaohongshu"
)

function New-PublishContext {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][ValidateSet("DryRun", "Draft", "Publish")][string]$Mode,
        [string]$Cover16x9,
        [string]$Cover3x4
    )

    $date = Get-Date -Format "yyyy-MM-dd"
    $dailyOutDir = Join-Path $Root "out\$date"
    if ([string]::IsNullOrWhiteSpace($Cover16x9)) {
        $Cover16x9 = Join-Path $dailyOutDir "16-9.png"
    }
    if ([string]::IsNullOrWhiteSpace($Cover3x4)) {
        $Cover3x4 = Join-Path $dailyOutDir "3-4.png"
    }

    $logDir = Join-Path $Root "out\publish-logs\$date"
    New-Item -ItemType Directory -Force $logDir | Out-Null
    $dryRunRunId = Get-Date -Format "yyyyMMdd-HHmmss"
    $dryRunLatestJson = Join-Path $Root "out\dryrun-latest.json"
    $dryRunDatedJson = Join-Path $Root "out\$date\dryrun-$dryRunRunId.json"

    $dryRunRecord = $null
    if ($Mode -eq "DryRun") {
        $dryRunRecord = [ordered]@{
            run_id = $dryRunRunId
            mode = $Mode
            started_at = (Get-Date).ToString("o")
            finished_at = $null
            overall_status = "running"
            platforms = [ordered]@{}
        }
    }

    [pscustomobject]@{
        Root = $Root
        Mode = $Mode
        Session = "publish"
        PublishProfile = "E:\社区账号\browser-profiles\publish"
        DraftUrl = "http://localhost:8010/draft-latest.html"
        PlatformPackUrl = "http://localhost:8010/platform-pack-latest.html"
        PlatformPackJson = Join-Path $Root "out\platform-pack-latest.json"
        DraftMarkdown = Join-Path $Root "out\draft-latest.md"
        LogDir = $logDir
        RunLog = Join-Path $logDir "publish-run.log"
        Cover16x9 = $Cover16x9
        Cover3x4 = $Cover3x4
        CurrentPlatform = ""
        DryRunRecord = $dryRunRecord
        DryRunLatestJson = $dryRunLatestJson
        DryRunDatedJson = $dryRunDatedJson
    }
}

function Save-DryRunRecord {
    param([Parameter(Mandatory = $true)]$Context)

    if ($Context.Mode -ne "DryRun" -or -not $Context.DryRunRecord) {
        return
    }

    $records = @($Context.DryRunRecord.platforms.Values)
    if ($records.Count -eq 0) {
        $Context.DryRunRecord.overall_status = "running"
    } elseif ($records | Where-Object { $_.status -in @("failed", "needs_manual") }) {
        $Context.DryRunRecord.overall_status = "partial"
    } elseif ($records | Where-Object { $_.status -eq "running" }) {
        $Context.DryRunRecord.overall_status = "running"
    } else {
        $Context.DryRunRecord.overall_status = "passed"
    }
    $Context.DryRunRecord.finished_at = if ($Context.DryRunRecord.overall_status -eq "running") { $null } else { (Get-Date).ToString("o") }
    $json = $Context.DryRunRecord | ConvertTo-Json -Depth 20
    Set-Content -LiteralPath $Context.DryRunLatestJson -Value $json -Encoding UTF8
    New-Item -ItemType Directory -Force (Split-Path -Parent $Context.DryRunDatedJson) | Out-Null
    Set-Content -LiteralPath $Context.DryRunDatedJson -Value $json -Encoding UTF8
}

function Write-DryRunPlatformResult {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)][string]$Platform,
        [Parameter(Mandatory = $true)][ValidateSet("running", "passed", "needs_manual", "failed", "skipped")][string]$Status,
        $State = $null,
        [string[]]$AvailableFields = @(),
        [string[]]$MissingFields = @(),
        [string]$ErrorMessage = ""
    )

    if ($Context.Mode -ne "DryRun" -or -not $Context.DryRunRecord) {
        return
    }

    $entryTerms = @()
    $loginTerms = @()
    $challengeTerms = @()
    $pageErrors = @()
    $pageUrl = ""
    $pageTitle = ""
    if ($State) {
        $pageUrl = [string]$State.url
        $pageTitle = [string]$State.title
        $entryTerms = @($State.entryTerms | ForEach-Object { [string]$_ })
        $loginTerms = @($State.loginTerms | ForEach-Object { [string]$_ })
        $challengeTerms = @($State.challengeTerms | ForEach-Object { [string]$_ })
        $pageErrors = @($State.errors | ForEach-Object { Protect-LogText ([string]$_) })
    }
    $Context.DryRunRecord.platforms[$Platform] = [ordered]@{
        status = $Status
        url = $pageUrl
        page_title = $pageTitle
        entry_detected = ($entryTerms.Count -gt 0)
        entry_terms = $entryTerms
        login_detected = ($loginTerms.Count -gt 0)
        login_terms = $loginTerms
        challenge_detected = ($challengeTerms.Count -gt 0)
        challenge_terms = $challengeTerms
        available_fields = @($AvailableFields)
        missing_fields = @($MissingFields)
        error = if ($ErrorMessage) { Protect-LogText $ErrorMessage } elseif ($pageErrors.Count -gt 0) { $pageErrors -join " | " } else { $null }
        checked_at = (Get-Date).ToString("o")
    }
    Save-DryRunRecord $Context
}
function Write-PublishLog {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)][string]$Message,
        [ValidateSet("INFO", "WARN", "ERROR")][string]$Level = "INFO"
    )

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $prefix = if ($Context.CurrentPlatform) { "[$($Context.CurrentPlatform)]" } else { "[run]" }
    $line = "$timestamp [$Level] $prefix $Message"
    Add-Content -LiteralPath $Context.RunLog -Value $line -Encoding UTF8

    if ($Context.CurrentPlatform) {
        $platformLog = Join-Path $Context.LogDir "$($Context.CurrentPlatform).log"
        Add-Content -LiteralPath $platformLog -Value $line -Encoding UTF8
    }

    Write-Host $line
}

function Protect-LogText {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) {
        return ""
    }

    $redacted = $Text
    $redacted = [regex]::Replace($redacted, "(?i)(cookie|token|authorization|passwd|password|secret|session)[^`r`n]{0,120}", '$1=[REDACTED]')
    $redacted = [regex]::Replace($redacted, "(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]+", '$1[REDACTED]')
    if ($redacted.Length -gt 1200) {
        $redacted = $redacted.Substring(0, 1200) + "...[truncated]"
    }
    return $redacted
}

function Invoke-PublishCli {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$Raw,
        [switch]$LogOutput
    )

    foreach ($arg in $Arguments) {
        if ($arg -eq "delete-data") {
            throw "Refusing to run playwright-cli delete-data for publish profile."
        }
    }

    $fullArgs = @()
    if ($Raw) {
        $fullArgs += "--raw"
    }
    $fullArgs += "-s=$($Context.Session)"
    $fullArgs += $Arguments

    Write-PublishLog $Context ("playwright-cli " + (($fullArgs | ForEach-Object {
        if ($_ -match "\s") { '"' + $_ + '"' } else { $_ }
    }) -join " "))

    $output = & playwright-cli @fullArgs 2>&1 | Out-String
    $exitCode = $LASTEXITCODE

    if ($LogOutput -and $output) {
        Write-PublishLog $Context (Protect-LogText $output)
    }

    if ($exitCode -ne 0) {
        $safeOutput = Protect-LogText $output
        Write-PublishLog $Context "playwright-cli failed with exit code $exitCode. $safeOutput" "WARN"
        throw "playwright-cli failed with exit code $exitCode."
    }

    return $output.Trim()
}

function Ensure-PublishBrowser {
    param([Parameter(Mandatory = $true)]$Context)

    if (-not (Test-Path -LiteralPath $Context.PublishProfile)) {
        New-Item -ItemType Directory -Force $Context.PublishProfile | Out-Null
        Write-PublishLog $Context "Created publish profile directory: $($Context.PublishProfile)"
        Write-PublishLog $Context "First login still needs manual browser setup for each platform." "WARN"
    }

    Invoke-PublishCli $Context @(
        "open",
        "--browser=chrome",
        "--profile=$($Context.PublishProfile)",
        $Context.PlatformPackUrl
    ) | Out-Null
}

function Open-PublishUrl {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)][string]$Url
    )

    try {
        Invoke-PublishCli $Context @("goto", $Url) | Out-Null
    } catch {
        Write-PublishLog $Context "goto failed; opening publish browser with persistent profile." "WARN"
        Invoke-PublishCli $Context @(
            "open",
            "--browser=chrome",
            "--profile=$($Context.PublishProfile)",
            $Url
        ) | Out-Null
    }
}

function Invoke-BrowserFunction {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)][string]$FunctionSource,
        [string]$Name = "browser-action"
    )

    $safeName = ($Name -replace "[^A-Za-z0-9_-]", "-")
    $file = Join-Path $Context.LogDir ("tmp-$safeName-" + (Get-Date -Format "HHmmssfff") + ".run-code.js")
    Set-Content -LiteralPath $file -Value $FunctionSource -Encoding UTF8
    try {
        $raw = Invoke-PublishCli $Context @("run-code", "--filename=$file") -Raw
        if ([string]::IsNullOrWhiteSpace($raw)) {
            return $null
        }
        $trimmed = $raw.Trim()
        if ($trimmed -notmatch '^[\[{\"]') {
            throw "playwright-cli returned a non-JSON result: $(Protect-LogText $trimmed)"
        }
        $parsed = $trimmed | ConvertFrom-Json
        if ($parsed -is [string]) {
            if ($parsed.Trim() -notmatch '^[\[{\"]') {
                throw "browser function returned a non-JSON payload: $(Protect-LogText $parsed)"
            }
            return ($parsed | ConvertFrom-Json)
        }
        return $parsed
    } finally {
        Remove-Item -LiteralPath $file -Force
    }
}

function Wait-ManualAction {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)][string]$Reason
    )

    Write-PublishLog $Context "Paused for manual action: $Reason" "WARN"
    Write-Host ""
    Write-Host "需要你手动处理：$Reason"
    Write-Host "处理完成后回到终端按 Enter 继续。"
    [void](Read-Host)
}

function Read-JsonFile {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Missing file: $Path"
    }
    return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
}

function ConvertTo-PlainArticleText {
    param([string]$Markdown)
    if ([string]::IsNullOrWhiteSpace($Markdown)) {
        return ""
    }

    $lines = New-Object System.Collections.Generic.List[string]
    $inComment = $false
    foreach ($rawLine in ($Markdown -split "`r?`n")) {
        $line = $rawLine.Trim()
        if ($line.StartsWith("<!--")) {
            $inComment = $true
            continue
        }
        if ($inComment) {
            if ($line.EndsWith("-->")) {
                $inComment = $false
            }
            continue
        }
        if ($line -eq "---") {
            continue
        }
        $line = [regex]::Replace($line, '^\s{0,3}#{1,6}\s+', '')
        $line = [regex]::Replace($line, '^\s*[-*]\s+', '')
        $line = [regex]::Replace($line, '^\s*\d+\.\s+', '')
        $line = [regex]::Replace($line, '\*\*([^*]+)\*\*', '$1')
        $tick = [regex]::Escape([string][char]96)
        $inlineCodePattern = $tick + '([^' + $tick + ']+)' + $tick
        $line = [regex]::Replace($line, $inlineCodePattern, '$1')
        $line = [regex]::Replace($line, '\[([^\]]+)\]\((https?://[^)]+)\)', '$1 ($2)')
        if ($line) {
            $lines.Add($line) | Out-Null
        }
    }
    return ($lines -join "`n`n").Trim()
}

function Remove-MarkdownMetaComment {
    param([string]$Markdown)
    if ([string]::IsNullOrWhiteSpace($Markdown)) {
        return ""
    }

    $lines = New-Object System.Collections.Generic.List[string]
    $inComment = $false
    foreach ($rawLine in ($Markdown -split "`r?`n")) {
        $line = $rawLine.Trim()
        if ($line.StartsWith("<!--")) {
            $inComment = $true
            continue
        }
        if ($inComment) {
            if ($line.EndsWith("-->")) {
                $inComment = $false
            }
            continue
        }
        $lines.Add($rawLine) | Out-Null
    }
    return (($lines -join "`n").Trim() + "`n")
}

function ConvertTo-DouyinImportText {
    param([string]$Markdown)

    $clean = Remove-MarkdownMetaComment $Markdown
    $lines = New-Object System.Collections.Generic.List[string]
    $skipSources = $false
    foreach ($rawLine in ($clean -split "`r?`n")) {
        $line = $rawLine.TrimEnd()
        if ($line -match '^\s{0,3}#{1,6}\s+来源链接\s*$') {
            $skipSources = $true
            continue
        }
        if ($skipSources) {
            continue
        }
        $line = [regex]::Replace($line, '\[([^\]]+)\]\((https?://[^)]+)\)', '$1')
        $line = [regex]::Replace($line, '<https?://[^>]+>', '')
        $line = [regex]::Replace($line, 'https?://\S+', '')
        $lines.Add($line) | Out-Null
    }
    return (($lines -join "`n").Trim() + "`n")
}

function Resolve-ImportFilePath {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)][string]$Kind
    )

    if (-not (Test-Path -LiteralPath $Context.DraftMarkdown)) {
        throw "Missing draft markdown: $($Context.DraftMarkdown)"
    }

    $raw = Get-Content -LiteralPath $Context.DraftMarkdown -Raw -Encoding UTF8
    if ($Kind -eq "douyin") {
        $path = Join-Path $Context.Root "out\publish-draft-latest-douyin.txt"
        Set-Content -LiteralPath $path -Value (ConvertTo-DouyinImportText $raw) -Encoding UTF8
        Write-PublishLog $Context "Prepared Douyin import text: $path"
        return $path
    }

    $path = Join-Path $Context.Root "out\publish-draft-latest.md"
    Set-Content -LiteralPath $path -Value (Remove-MarkdownMetaComment $raw) -Encoding UTF8
    Write-PublishLog $Context "Prepared clean markdown import file: $path"
    return $path
}

function Get-PlatformPackFromDom {
    param([Parameter(Mandatory = $true)]$Context)

    $packUrl = $Context.PlatformPackUrl.Replace("\", "\\").Replace("'", "\'")
    $draftUrl = $Context.DraftUrl.Replace("\", "\\").Replace("'", "\'")

    $js = @'
async page => {
  const result = { source: 'dom', platforms: {}, article: { title: '', text: '' }, errors: [] };
  try {
    await page.goto('__PACK_URL__', { waitUntil: 'domcontentloaded', timeout: 30000 });
    const fields = await page.locator('[data-platform][data-field]').evaluateAll(nodes => nodes.map(node => {
      let items = [];
      try { items = JSON.parse(node.getAttribute('data-items') || '[]'); } catch (_) { items = []; }
      return {
        platform: node.getAttribute('data-platform') || '',
        field: node.getAttribute('data-field') || '',
        value: node.getAttribute('data-value') || '',
        items,
        length: Number(node.getAttribute('data-length') || '0'),
        max: node.getAttribute('data-max') || ''
      };
    }));
    for (const field of fields) {
      if (!field.platform || !field.field) continue;
      result.platforms[field.platform] ||= {};
      result.platforms[field.platform][field.field] = field.items && field.items.length > 1 ? field.items : field.value;
      result.platforms[field.platform]._meta ||= {};
      result.platforms[field.platform]._meta[field.field] = { length: field.length, max: field.max };
    }
  } catch (error) {
    result.errors.push('platform pack DOM read failed: ' + error.message);
  }

  try {
    await page.goto('__DRAFT_URL__', { waitUntil: 'domcontentloaded', timeout: 30000 });
    result.article.title = await page.locator('#article h1').first().innerText({ timeout: 2000 }).catch(() => '');
    result.article.text = await page.locator('#article').first().innerText({ timeout: 3000 }).catch(() => '');
  } catch (error) {
    result.errors.push('draft DOM read failed: ' + error.message);
  }
  return JSON.stringify(result);
}
'@
    $js = $js.Replace("__PACK_URL__", $packUrl).Replace("__DRAFT_URL__", $draftUrl)

    return Invoke-BrowserFunction $Context $js "read-pack-dom"
}

function Get-PlatformPack {
    param([Parameter(Mandatory = $true)]$Context)

    Write-PublishLog $Context "Reading platform fields from DOM."
    $dom = $null
    try {
        $dom = Get-PlatformPackFromDom $Context
    } catch {
        Write-PublishLog $Context "DOM field read failed, falling back to JSON. $($_.Exception.Message)" "WARN"
    }

    $platforms = @{}
    $article = [pscustomobject]@{ title = ""; text = "" }

    if ($dom -and $dom.platforms) {
        foreach ($property in $dom.platforms.PSObject.Properties) {
            $platforms[$property.Name] = $property.Value
        }
        $article = $dom.article
    }

    if ($platforms.Count -eq 0) {
        Write-PublishLog $Context "Reading platform fields from out/platform-pack-latest.json." "WARN"
        $json = Read-JsonFile $Context.PlatformPackJson
        foreach ($property in $json.PSObject.Properties) {
            $platforms[$property.Name] = $property.Value
        }
    }

    if ([string]::IsNullOrWhiteSpace($article.text) -and (Test-Path -LiteralPath $Context.DraftMarkdown)) {
        $markdown = Get-Content -LiteralPath $Context.DraftMarkdown -Raw -Encoding UTF8
        $article = [pscustomobject]@{
            title = (($markdown -split "`r?`n" | Where-Object { $_ -match "^#\s+" } | Select-Object -First 1) -replace "^#\s+", "")
            text = ConvertTo-PlainArticleText $markdown
        }
    }

    Write-PublishLog $Context ("Loaded platform data for: " + (($platforms.Keys | Sort-Object) -join ", "))
    Write-PublishLog $Context ("Article text length: " + (($article.text | Out-String).Length))

    return [pscustomobject]@{
        Platforms = $platforms
        Article = $article
    }
}

function Get-PlatformData {
    param(
        [Parameter(Mandatory = $true)]$Pack,
        [Parameter(Mandatory = $true)][string]$Platform
    )

    if (-not $Pack.Platforms.ContainsKey($Platform)) {
        throw "Platform data missing: $Platform"
    }
    return $Pack.Platforms[$Platform]
}

function Get-DataValue {
    param(
        [Parameter(Mandatory = $true)]$Data,
        [Parameter(Mandatory = $true)][string]$Field,
        $Default = ""
    )

    if ($Data.PSObject.Properties.Name -contains $Field) {
        return $Data.$Field
    }
    return $Default
}

function ConvertTo-JsonLiteral {
    param([Parameter(Mandatory = $true)]$Value)
    return ($Value | ConvertTo-Json -Depth 30 -Compress)
}

function Resolve-CoverPath {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)][string]$Ratio
    )

    if ($Ratio -eq "3:4") {
        $path = $Context.Cover3x4
    } else {
        $path = $Context.Cover16x9
    }

    while ([string]::IsNullOrWhiteSpace($path) -or -not (Test-Path -LiteralPath $path)) {
        Write-PublishLog $Context "Missing cover path for ratio $Ratio." "WARN"
        $path = Read-Host "Enter full path for $Ratio cover, or press Enter to skip upload and handle it manually"
        if ([string]::IsNullOrWhiteSpace($path)) {
            return ""
        }
    }

    return (Resolve-Path -LiteralPath $path).Path
}

function Test-PlatformPageState {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)]$Spec
    )

    $entryHints = ConvertTo-JsonLiteral ($Spec.EntryHints)
    $js = @'
async page => {
  const entryHints = __ENTRY_HINTS__;
  const result = {
    url: '', title: '', challengeTerms: [], loginTerms: [], entryTerms: [], buttonCount: 0, errors: []
  };
  try { result.url = page.url(); } catch (error) { result.errors.push('url: ' + error.message); }
  try { result.title = await page.title(); } catch (error) { result.errors.push('title: ' + error.message); }
  try {
    await page.waitForLoadState('domcontentloaded').catch(() => {});
    await page.waitForTimeout(2000);
    const bodyText = await page.locator('body').innerText({ timeout: 5000 }).catch(() => '');
    const limited = bodyText.slice(0, 20000);
    const challengePatterns = ['验证码','扫码','二维码','短信验证','安全验证','滑块','拖动滑块','captcha','verify','verification','risk control'];
    const loginPatterns = ['登录','登陆','Sign in','Log in','login','未登录'];
    result.challengeTerms = challengePatterns.filter(term => limited.toLowerCase().includes(term.toLowerCase()));
    result.loginTerms = loginPatterns.filter(term => limited.toLowerCase().includes(term.toLowerCase()));
    result.entryTerms = entryHints.filter(term => limited.includes(term));
    const buttons = await page.locator('button, [role=button], a').evaluateAll(nodes => nodes.slice(0, 80).map(node => (node.innerText || node.textContent || '').trim()).filter(Boolean)).catch(() => []);
    result.buttonCount = buttons.length;
  } catch (error) {
    result.errors.push('page state: ' + error.message);
  }
  return JSON.stringify(result);
}
'@
    $js = $js.Replace("__ENTRY_HINTS__", $entryHints)
    try {
        return Invoke-BrowserFunction $Context $js "page-state-$($Spec.Key)"
    } catch {
        return [pscustomobject]@{
            url = ""
            title = ""
            challengeTerms = @()
            loginTerms = @()
            entryTerms = @()
            buttonCount = 0
            errors = @((Protect-LogText $_.Exception.Message))
        }
    }
}

function Invoke-DraftFill {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)]$Spec,
        [Parameter(Mandatory = $true)]$Payload
    )

    $json = ConvertTo-JsonLiteral $Payload
    $js = @'
async page => {
  const payload = __PAYLOAD__;
  const actions = [];
  const missing = [];
  const errors = [];

  async function fillLocator(locator, value, name) {
    try {
      await locator.first().waitFor({ state: 'attached', timeout: 1500 });
      const count = await locator.count();
      if (!count) return false;
      const first = locator.first();
      const tag = await first.evaluate(el => el.tagName.toLowerCase()).catch(() => '');
      const editable = await first.evaluate(el => el.isContentEditable).catch(() => false);
      if (tag === 'textarea' || tag === 'input' || editable) {
        await first.fill(String(value), { timeout: 2500 }).catch(async () => {
          await first.evaluate((el, text) => {
            if ('value' in el) {
              el.value = text;
            } else {
              el.textContent = text;
            }
            el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
          }, String(value));
        });
      } else {
        await first.evaluate((el, text) => {
          el.textContent = text;
          el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }, String(value));
      }
      actions.push('filled ' + name);
      return true;
    } catch (error) {
      errors.push(name + ': ' + error.message);
      return false;
    }
  }

  async function fillBySelectors(name, selectors, value) {
    if (!value || !selectors || !selectors.length) return true;
    for (const selector of selectors) {
      if (await fillLocator(page.locator(selector), value, name)) return true;
    }
    missing.push(name);
    return false;
  }

  async function clickByText(name, texts, forbidden) {
    if (!texts || !texts.length) return true;
    for (const text of texts) {
      if (forbidden && forbidden.some(term => text.includes(term))) continue;
      const locators = [
        page.getByRole('button', { name: text, exact: false }),
        page.getByText(text, { exact: false })
      ];
      for (const locator of locators) {
        try {
          if (await locator.count()) {
            await locator.first().click({ timeout: 1800 });
            actions.push('clicked ' + name + ': ' + text);
            await page.waitForTimeout(500);
            return true;
          }
        } catch (error) {
          errors.push(name + ': ' + error.message);
        }
      }
    }
    missing.push(name);
    return false;
  }

  async function addList(name, selectors, values) {
    if (!values || !values.length) return true;
    const items = Array.isArray(values) ? values : String(values).split(/\r?\n/).filter(Boolean);
    if (!items.length) return true;
    for (const selector of selectors || []) {
      const locator = page.locator(selector);
      try {
        if (!(await locator.count())) continue;
        for (const item of items) {
          await locator.first().fill(String(item), { timeout: 1500 });
          await page.keyboard.press('Enter');
          await page.waitForTimeout(300);
        }
        actions.push('added ' + name + ': ' + items.length);
        return true;
      } catch (error) {
        errors.push(name + ': ' + error.message);
      }
    }
    missing.push(name);
    return false;
  }

  async function importMarkdown(path, clickTexts) {
    if (!path) return false;
    try {
      let openedImport = false;
      for (const text of clickTexts || []) {
        const locators = [
          page.getByRole('button', { name: text, exact: false }),
          page.getByText(text, { exact: false })
        ];
        for (const locator of locators) {
          if (await locator.count()) {
            const chooserPromise = page.waitForEvent('filechooser', { timeout: 2000 }).catch(() => null);
            await locator.first().click({ timeout: 1800 }).catch(() => {});
            await page.waitForTimeout(700);
            openedImport = true;
            const chooser = await chooserPromise;
            if (chooser) {
              await chooser.setFiles(path);
              actions.push('imported markdown');
              await page.waitForTimeout(2500);
              return true;
            }
            break;
          }
        }
      }

      if (!openedImport) {
        missing.push('markdown import entry');
        return false;
      }

      const inputs = page.locator('input[type=file]');
      const count = await inputs.count();
      for (let i = 0; i < count; i++) {
        const input = inputs.nth(i);
        const accept = await input.getAttribute('accept').catch(() => '');
        if (!accept || /\.md|markdown|text|\*/i.test(accept)) {
          await input.setInputFiles(path);
          actions.push('imported markdown');
          await page.waitForTimeout(2500);
          return true;
        }
      }
    } catch (error) {
      errors.push('markdown import: ' + error.message);
    }
    missing.push('markdown import');
    return false;
  }

  async function uploadCover(path, clickTexts) {
    if (!path) {
      actions.push('cover upload skipped');
      return true;
    }
    try {
      let openedCover = false;
      for (const text of clickTexts || []) {
        const button = page.getByText(text, { exact: false });
        if (await button.count()) {
          const chooserPromise = page.waitForEvent('filechooser', { timeout: 2000 }).catch(() => null);
          await button.first().click({ timeout: 1500 }).catch(() => {});
          await page.waitForTimeout(500);
          openedCover = true;
          const chooser = await chooserPromise;
          if (chooser) {
            await chooser.setFiles(path);
            actions.push('uploaded cover');
            await page.waitForTimeout(1000);
            return true;
          }
          break;
        }
      }

      if (!openedCover) {
        missing.push('cover entry');
        return false;
      }

      const inputs = page.locator('input[type=file]');
      const count = await inputs.count();
      for (let i = 0; i < count; i++) {
        const input = inputs.nth(i);
        const accept = await input.getAttribute('accept').catch(() => '');
        if (!accept || /image|\*/i.test(accept)) {
          await input.setInputFiles(path);
          actions.push('uploaded cover');
          await page.waitForTimeout(1000);
          return true;
        }
      }
    } catch (error) {
      errors.push('cover: ' + error.message);
    }
    missing.push('cover upload');
    return false;
  }

  if (payload.preClickTexts && payload.preClickTexts.length) {
    for (const item of payload.preClickTexts) {
      await clickByText('pre-step', [item], ['发布']);
    }
  }

  const importedMarkdown = await importMarkdown(payload.importMarkdownPath, payload.importClickTexts);
  await fillBySelectors('title', payload.selectors.title, payload.fields.title);
  if (!importedMarkdown || !payload.skipBodyFillAfterImport) {
    await fillBySelectors('body', payload.selectors.body, payload.fields.body);
  }
  if (payload.openSettingsTexts && payload.openSettingsTexts.length) {
    await clickByText('open publish settings', payload.openSettingsTexts, []);
    await page.waitForTimeout(1200);
  }
  await fillBySelectors('summary', payload.selectors.summary, payload.fields.summary);
  await addList('topics', payload.selectors.topics, payload.fields.topics);
  await addList('tags', payload.selectors.tags, payload.fields.tags);
  await addList('hashtags', payload.selectors.hashtags, payload.fields.hashtags);

  if (payload.fields.category) {
    await clickByText('category', [payload.fields.category], ['发布']);
  }
  if (payload.fields.ai_statement) {
    await clickByText('ai statement', [payload.fields.ai_statement, 'AI 辅助', 'AI辅助'], ['发布']);
  }

  await uploadCover(payload.coverPath, payload.coverClickTexts);

  if (payload.saveDraftTexts && payload.saveDraftTexts.length) {
    const beforeMissing = missing.length;
    await clickByText('save draft', payload.saveDraftTexts, ['发布']);
    if (payload.saveOptional && missing.length > beforeMissing) {
      missing.pop();
      actions.push('save draft not found; marked optional');
    }
  }

  return JSON.stringify({
    url: page.url(),
    title: await page.title().catch(() => ''),
    actions,
    missing,
    errors
  });
}
'@
    $js = $js.Replace("__PAYLOAD__", $json)

    return Invoke-BrowserFunction $Context $js "draft-$($Spec.Key)"
}

function Invoke-FinalPublishClick {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)]$Spec
    )

    $texts = ConvertTo-JsonLiteral ($Spec.PublishTexts)
    $js = @'
async page => {
  const texts = __PUBLISH_TEXTS__;
  const candidates = [];
  for (const text of texts) {
    const locator = page.getByRole('button', { name: text, exact: false });
    const count = await locator.count().catch(() => 0);
    for (let i = 0; i < count; i++) {
      const item = locator.nth(i);
      const box = await item.boundingBox().catch(() => null);
      if (box) candidates.push({ text, index: i });
    }
  }
  if (candidates.length !== 1) {
    return JSON.stringify({ clicked: false, reason: 'publish button count is ' + candidates.length, candidates });
  }
  const target = page.getByRole('button', { name: candidates[0].text, exact: false }).nth(candidates[0].index);
  await target.click({ timeout: 3000 });
  return JSON.stringify({ clicked: true, text: candidates[0].text, url: page.url() });
}
'@
    $js = $js.Replace("__PUBLISH_TEXTS__", $texts)

    return Invoke-BrowserFunction $Context $js "publish-$($Spec.Key)"
}

function New-PlatformPayload {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)]$Spec,
        [Parameter(Mandatory = $true)]$Pack
    )

    $data = Get-PlatformData $Pack $Spec.Key
    $body = Get-DataValue $data "body" ""
    if ([string]::IsNullOrWhiteSpace([string]$body)) {
        $body = $Pack.Article.text
    }

    $title = Get-DataValue $data "title" ""
    if ([string]::IsNullOrWhiteSpace([string]$title)) {
        $title = $Pack.Article.title
    }

    $coverPath = ""
    if ($Context.Mode -ne "DryRun") {
        $coverPath = Resolve-CoverPath $Context $Spec.CoverRatio
    }

    $topics = Get-DataValue $data "topics" @()
    if ($Spec.Key -eq "bilibili") {
        $topic = Get-DataValue $data "topic" ""
        $topics = if ($topic) { @($topic) } else { @() }
    }

    return [pscustomobject]@{
        fields = [pscustomobject]@{
            title = [string]$title
            body = [string]$body
            summary = [string](Get-DataValue $data "summary" "")
            category = [string](Get-DataValue $data "category" "")
            ai_statement = [string](Get-DataValue $data "ai_statement" "")
            topics = $topics
            tags = Get-DataValue $data "tags" @()
            hashtags = Get-DataValue $data "hashtags" @()
        }
        selectors = $Spec.Selectors
        coverPath = $coverPath
        coverClickTexts = $Spec.CoverClickTexts
        preClickTexts = $Spec.PreClickTexts
        openSettingsTexts = if ($Spec.PSObject.Properties.Name -contains "OpenSettingsTexts") { $Spec.OpenSettingsTexts } else { @() }
        importMarkdownPath = if ($Spec.PSObject.Properties.Name -contains "ImportMarkdown" -and $Spec.ImportMarkdown) {
            $importKind = if ($Spec.PSObject.Properties.Name -contains "ImportKind") { [string]$Spec.ImportKind } else { "markdown" }
            Resolve-ImportFilePath $Context $importKind
        } else { "" }
        importClickTexts = if ($Spec.PSObject.Properties.Name -contains "ImportClickTexts") { $Spec.ImportClickTexts } else { @() }
        skipBodyFillAfterImport = if ($Spec.PSObject.Properties.Name -contains "SkipBodyFillAfterImport") { [bool]$Spec.SkipBodyFillAfterImport } else { $false }
        saveDraftTexts = $Spec.SaveDraftTexts
        saveOptional = [bool]$Spec.SaveOptional
    }
}

function Invoke-GenericPlatform {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)]$Spec,
        [Parameter(Mandatory = $true)]$Pack
    )

    $Context.CurrentPlatform = $Spec.Key
    Write-PublishLog $Context "Starting $($Context.Mode) for $($Spec.Key)."
    Open-PublishUrl $Context $Spec.Url

    $state = Test-PlatformPageState $Context $Spec
    Write-PublishLog $Context "Page title: $($state.title)"
    Write-PublishLog $Context "Page URL: $($state.url)"
    if ($state.challengeTerms -and $state.challengeTerms.Count -gt 0) {
        Wait-ManualAction $Context ("detected verification or risk prompt: " + ($state.challengeTerms -join ", "))
    }
    if ($state.loginTerms -and $state.loginTerms.Count -gt 0 -and -not ($state.entryTerms -and $state.entryTerms.Count -gt 0)) {
        Wait-ManualAction $Context ("login may be expired; detected: " + ($state.loginTerms -join ", "))
    }
    if (-not ($state.entryTerms -and $state.entryTerms.Count -gt 0)) {
        Wait-ManualAction $Context "key publish entry was not confidently detected on this page"
    }

    if ($Context.Mode -eq "DryRun") {
        $data = Get-PlatformData $Pack $Spec.Key
        $fieldNames = ($data.PSObject.Properties.Name | Where-Object { $_ -ne "_meta" } | Sort-Object) -join ", "
        $status = "passed"
        if ($state.errors -and $state.errors.Count -gt 0) {
            $status = "failed"
        } elseif (($state.challengeTerms -and $state.challengeTerms.Count -gt 0) -or ($state.loginTerms -and $state.loginTerms.Count -gt 0) -or -not ($state.entryTerms -and $state.entryTerms.Count -gt 0)) {
            $status = "needs_manual"
        }
        Write-DryRunPlatformResult $Context $Spec.Key $status $state ($fieldNames -split ", " | Where-Object { $_ }) @() ""
        Write-PublishLog $Context "DryRun completed. Fields available: $fieldNames"
        return
    }

    if ($Spec.ManualBeforeDraft) {
        Wait-ManualAction $Context $Spec.ManualBeforeDraft
    }

    $payload = New-PlatformPayload $Context $Spec $Pack
    $draftResult = Invoke-DraftFill $Context $Spec $payload
    Write-PublishLog $Context ("Draft actions: " + (($draftResult.actions | ForEach-Object { $_ }) -join "; "))
    if ($draftResult.missing -and $draftResult.missing.Count -gt 0) {
        Wait-ManualAction $Context ("missing or uncertain controls: " + ($draftResult.missing -join ", "))
    }
    if ($draftResult.errors -and $draftResult.errors.Count -gt 0) {
        Write-PublishLog $Context ("Non-sensitive automation errors: " + (($draftResult.errors | Select-Object -First 5) -join " | ")) "WARN"
    }

    if ($Context.Mode -eq "Draft") {
        Write-PublishLog $Context "Draft mode completed; no final publish action was attempted."
        return
    }

    if ($Context.Mode -eq "Publish") {
        Write-Host ""
        $confirm = Read-Host "Type YES to finally publish $($Spec.Key). Anything else skips final publish"
        if ($confirm -ne "YES") {
            Write-PublishLog $Context "Publish skipped because confirmation was not YES." "WARN"
            return
        }
        $publishResult = Invoke-FinalPublishClick $Context $Spec
        if (-not $publishResult.clicked) {
            Wait-ManualAction $Context ("final publish button was not uniquely identified: " + $publishResult.reason)
        } else {
            Write-PublishLog $Context "Final publish clicked after YES confirmation."
        }
    }
}
function Assert-HumanReviewApproved {
    param([Parameter(Mandatory = $true)]$Context)

    $reviewPath = Join-Path $Context.Root "out\article-review-latest.json"
    $review = Read-JsonFile $reviewPath
    $status = [string]$review.review_status
    if ([string]::IsNullOrWhiteSpace($status) -and $review.human_review) {
        $status = [string]$review.human_review.status
    }
    if ($status -ne "approved") {
        throw "Human review is not approved. Current status: $status. Use the review page before Draft or Publish mode."
    }
    Write-PublishLog $Context "Human review approved; platform sync may continue."
}

function Assert-PlatformReviewApproved {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)][string[]]$Platforms
    )

    $reviewPath = Join-Path $Context.Root "out\platform-review-latest.json"
    $review = Read-JsonFile $reviewPath
    foreach ($platform in $Platforms) {
        $item = $review.platforms.$platform
        if (-not $item -or [string]$item.status -ne "approved") {
            throw "Platform review is not approved for $platform. Current status: $([string]$item.status)."
        }
    }
    Write-PublishLog $Context "Requested platform versions are human-approved; sync may continue."
}
