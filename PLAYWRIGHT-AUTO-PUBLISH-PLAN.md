```text
你现在在 Windows 项目目录 E:\社区账号\content-pipeline 中工作。

请使用 playwright-cli skill：
C:\Users\24696\.codex\skills\playwright-cli\SKILL.md

目标：
帮我制作一个“每日文章自动化发文脚本”。每天文章生成后，我会先人工审核文章质量，然后运行脚本，把今日文章和各平台字段自动填入平台后台。脚本必须先支持 DryRun 和 Draft，Publish 必须有最终确认，禁止默认直接发布。

数据来源：
1. 今日文章页面：
   http://localhost:8010/draft-latest.html
2. 各平台发布字段页面：
   http://localhost:8010/platform-pack-latest.html
3. 平台字段页面中已经有自动化友好的 DOM：
   - data-platform
   - data-field
   - data-value
   - data-items
   - data-length
   - data-max
4. 脚本应优先从页面 DOM 读取字段，也可以直接读取 out/platform-pack-latest.json 作为备用。

必须使用发布专用浏览器 profile，不能使用临时无登录态浏览器：
E:\社区账号\browser-profiles\publish

所有 playwright-cli 调用统一使用：
playwright-cli -s=publish ...

首次初始化命令可以写入文档或脚本提示中，但不要自动删除 profile：
New-Item -ItemType Directory -Force "E:\社区账号\browser-profiles\publish"
playwright-cli -s=publish open --browser=chrome --profile="E:\社区账号\browser-profiles\publish"

禁止执行：
playwright-cli -s=publish delete-data

不要发布这些平台：
- 微博
- 微信公众号
- 今日头条

只制作以下 6 个平台的自动化模块：
- 知乎 zhihu
- 稀土掘金 juejin
- B站 bilibili
- CSDN csdn
- 抖音 douyin
- 小红书 xiaohongshu

请创建或完善以下脚本结构：
scripts\publish_daily.ps1
scripts\publish\common.ps1
scripts\publish\platforms\zhihu.ps1
scripts\publish\platforms\juejin.ps1
scripts\publish\platforms\bilibili.ps1
scripts\publish\platforms\csdn.ps1
scripts\publish\platforms\douyin.ps1
scripts\publish\platforms\xiaohongshu.ps1

总控脚本 publish_daily.ps1 要支持：
- -Mode DryRun：只读取字段、打开平台页面、检查登录态和关键入口，不填入、不保存、不发布。
- -Mode Draft：填入正文和平台字段、上传封面、选择声明，最后只保存草稿，不最终发布。
- -Mode Publish：在 Draft 流程稳定后才允许使用；必须在终端要求输入 YES 才能点击最终发布。
- -Platforms zhihu,bilibili：允许只运行部分平台。
- 遇到验证码、扫码、短信验证、安全提醒、滑动验证、页面结构不确定时，必须暂停并提示我手动处理，等我按 Enter 后继续。

所有日志保存到：
E:\社区账号\content-pipeline\out\publish-logs\YYYY-MM-DD

日志不要保存 Cookie、Token、账号隐私、完整页面敏感内容。

平台规则：

1. 抖音 douyin
- 标题 title 最多 30 字
- 摘要 summary 最多 30 字
- 添加话题 hashtags
- 封面使用 3:4

2. 知乎 zhihu
- 填标题、正文、文章话题 topics
- 创作声明选择“包含 AI 辅助创作”
- 上传 16:9 封面

3. 稀土掘金 juejin
- 分类固定选择“人工智能”
- 添加标签 tags
- 如果标签搜索不到，就选“人工智能”
- 编辑摘要 summary 最多 100 字
- 上传 16:9 封面

4. B站 bilibili
- 点击“自定义封面”后上传 16:9 封面
- 创作声明点击“AI 辅助创作声明”
- 话题 topic 只能添加 1 个
- 如果搜索不到话题，就选择相关话题中热度最高的一个

5. CSDN csdn
- 添加文章标签 tags
- 摘要 summary 最多 256 字
- 创作声明选择“部分由 AI 辅助生成”
- 上传 16:9 封面

6. 小红书 xiaohongshu
- 打开右上角草稿箱中最新一篇
- 点击“一键排版”，等待完成
- 点击下一步
- 在图片编辑中添加 3:4 封面
- 内容类型声明选择“笔记包含 AI 合成内容”
- 添加话题 hashtags
- 标题 title 最多 20 字

封面规则：
- 默认使用 16:9 封面
- 抖音和小红书使用 3:4 封面
- 默认封面路径按当天输出目录读取：`out\YYYY-MM-DD\16-9.png` 和 `out\YYYY-MM-DD\3-4.png`。
- 例如 2026-06-05 使用：`E:\社区账号\content-pipeline\out\2026-06-05\16-9.png` 和 `E:\社区账号\content-pipeline\out\2026-06-05\3-4.png`。
- 仍然允许用 -Cover16x9 和 -Cover3x4 覆盖；缺失时暂停提示用户补充，不要乱选文件。

实现要求：
- 先阅读现有项目文件，尤其是 AGENTS.md、out/platform-pack-latest.json、site/platform-pack-latest.html、scripts/render_platform_pack_html.py。
- 不要批量删除文件，不要执行 Remove-Item -Recurse、rm -rf、rmdir /s。
- 不要改 .env，不要输出密钥。
- 优先实现稳健的字段读取、日志、暂停、DryRun。
- 平台页面结构可能变化，脚本要用清晰函数封装，并在找不到元素时暂停而不是盲点。
- 对每个平台先实现 DryRun 检查函数，再实现 Draft 填写函数。
- Publish 模式最后实现，并默认需要 YES 确认。
- 完成后运行本地语法检查；如果可以，只运行 DryRun，不要执行 Draft 或 Publish，除非我明确要求。

交付物：
1. 完成的 PowerShell 自动化脚本文件。
2. README 或脚本内注释说明如何运行：
   .\scripts\publish_daily.ps1 -Mode DryRun
   .\scripts\publish_daily.ps1 -Platforms zhihu -Mode DryRun
   .\scripts\publish_daily.ps1 -Mode Draft
   .\scripts\publish_daily.ps1 -Mode Publish
3. 明确列出哪些平台已实现、哪些入口需要我手动确认。
4. 明确说明没有执行真实发布。xxxxxxxxxx 能用 publish profile 打开浏览器能读取 platform-pack-latest.html 的 data-value 和 data-items能按平台进入发布页能检测登录态是否失效能保存每个平台的执行日志遇到验证码能暂停DryRun 不会误点击发布Draft 模式不会最终发布Publish 模式需要最终确认text
```
