# Daily Publish Automation

PowerShell entry point:

```powershell
.\scripts\publish_daily.ps1 -Mode DryRun
.\scripts\publish_daily.ps1 -Platforms zhihu -Mode DryRun
.\scripts\publish_daily.ps1 -Mode Draft
.\scripts\publish_daily.ps1 -Mode Publish
```

The script always uses the persistent publish profile:

```powershell
E:\社区账号\browser-profiles\publish
```

First-time setup can be done manually:

```powershell
New-Item -ItemType Directory -Force "E:\社区账号\browser-profiles\publish"
playwright-cli -s=publish open --browser=chrome --profile="E:\社区账号\browser-profiles\publish"
```

Do not run:

```powershell
playwright-cli -s=publish delete-data
```

Default cover paths:

```text
out\YYYY-MM-DD\16-9.png
out\YYYY-MM-DD\3-4.png
```

For example, on 2026-06-05 the script will use:

```text
E:\社区账号\content-pipeline\out\2026-06-05\16-9.png
E:\社区账号\content-pipeline\out\2026-06-05\3-4.png
```

You can still override these paths with `-Cover16x9` and `-Cover3x4`.

Modes:

- `DryRun`: reads `platform-pack-latest.html` DOM fields, falls back to `out/platform-pack-latest.json`, opens each platform publish page, and checks login/verification/entry hints. It does not fill, save, or publish.
- `Draft`: requires `out/article-review-latest.json` to have human review status `approved`, then fills the article and platform fields where selectors are confidently found, uploads the requested cover file, selects AI declarations when visible, and saves draft when a safe draft button is found. It never clicks final publish.
- `Publish`: also requires human review status `approved`, runs the Draft path first, and before any final publish click the terminal requires `YES` for that platform. Draft mode is the recommended mode when final publishing must remain manual.

Formatting and cover policy:

- Platforms that expose an import flow should import `out\draft-latest.md` instead of pasting Markdown into a rich-text editor.
- Markdown-native editors such as Juejin and CSDN can receive the Markdown body directly.
- Cover upload only runs after a clear cover entry is clicked, such as `添加文章封面`, `自定义封面`, or `上传封面`; the script should not use a body image toolbar as the cover entry.

Known platform entry points:

- Juejin: editor URL `https://juejin.cn/editor/drafts/new?v=2`; click `发布` to open the publish settings panel, then fill category/tags/summary and upload cover.
- Bilibili: article editor URL `https://member.bilibili.com/platform/upload/text/new-edit?aid=364875`; use the toolbar `导入文档` entry for article import and `自定义封面` for cover.
- CSDN: use `更多 -> 导入` for Markdown import; click `发布文章` to open the settings modal, then use `从本地上传` for cover.
- Xiaohongshu: article editor URL `https://creator.xiaohongshu.com/publish/publish?from=menu&target=article`; use `文档导入` for article import, then the image-edit/cover area for the 3:4 cover.
- Douyin: use the `发布文章` tab and `一键导入`; the imported file is `out\publish-draft-latest-douyin.txt`, which removes generation metadata and source-link material that Douyin may mark unsupported.

Logs are written under:

```text
out\publish-logs\YYYY-MM-DD
```

Logs intentionally avoid cookies, tokens, and full page content.

Implemented platform modules:

- `zhihu`
- `juejin`
- `bilibili`
- `csdn`
- `douyin`
- `xiaohongshu`

Manual confirmation is expected when a site shows captcha, QR login, SMS verification, risk warnings, slider checks, or when a publish/draft control cannot be uniquely identified. Bilibili, Douyin, and Xiaohongshu also have manual checkpoints because their current editor entry can vary by content type.
