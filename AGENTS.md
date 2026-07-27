# 社区账号内容生产流水线

## 一、常用使用命令（先看这里）

### 启动 Docker 服务

```powershell
Set-Location "E:\社区账号\content-pipeline"
docker compose up -d
docker ps
```

主要服务：n8n `http://localhost:5860`、预览站点 `http://localhost:8010`、Worker `http://localhost:8020/health`。

### 启动 Worker

```powershell
.\scripts\start_worker.ps1
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8020/health
```

### 日报模式

推荐在 n8n 中手动执行或按每日 19:10 自动执行 `Daily Tech Intelligence`。不要同时启用 n8n Schedule Trigger 和 Windows 计划任务 `ContentPipelineDailyDigest`。

### 指定主题模式

```powershell
.\scripts\generate_knowledge_share.ps1 `
  -Topic "好用的 Codex 插件分享" `
  -Angle "介绍使用场景、适合人群、配置方法和注意事项" `
  -TopResults 8 `
  -ReaderTimeout 18
```

### 查看和审核结果

```text
日报草稿：     http://localhost:8010/draft-latest.html
主题文章：     http://localhost:8010/knowledge-share-latest.html
内容池：       http://localhost:8010/content-pool-latest.html
主题候选：     http://localhost:8010/topic-candidates-latest.html
文章人工审核： http://localhost:8010/article-review-latest.html
平台版本审核： http://localhost:8010/platform-pack-latest.html
```

审核顺序：查看文章和来源 → 文章人工通过 → 查看平台版本 → 平台人工通过 → 按需执行 DryRun → 使用原有插件同步 → 人工确认并发布。

### 发布辅助 DryRun

```powershell
.\scripts\publish_daily.ps1 -Mode DryRun
```

DryRun 只检查平台入口、登录状态、验证码/风控和字段，不填写、不保存、不发布。

### 测试

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
Get-ChildItem scripts -Filter *.py | ForEach-Object { python -m py_compile $_.FullName }
python -m json.tool n8n-workflows\daily-tech-intel.json > $null
```

### Git 基本流程

```powershell
git switch main
git pull --ff-only origin main
git switch -c feat/<task-name>
# 修改、测试、检查
git add -- <明确文件>
git commit -m "<message>"
git push -u origin <branch-name>
```

完成后创建 Draft PR，人工审核后再合并。

## 二、项目整体流程和设计思想

```text
新闻或指定主题采集
→ 来源读取与去重
→ 内容筛选
→ AI 生成文章草稿
→ 事实、来源和质量检查
→ 人工审核文章
→ 生成不同平台版本
→ 人工审核平台版本
→ 浏览器插件辅助同步
→ 人工最终确认发布
```

核心思想：

- 生成和发布分离，AI 不直接发布内容；
- 所有文章默认进入人工审核；
- 平台版本独立审核，不把文章审核等同于平台审核；
- 保留来源、运行 ID、事实记录、审核记录和失败阶段；
- n8n 只负责定时调度，内容生产逻辑由脚本负责；
- 同一时间只启用一个每日调度器；
- 不绕过登录、验证码、风控或平台人工确认。

## 三、当前具体实现

### 内容生产

- `scripts/daily_digest.py`：日报采集、去重、筛选、事实卡、主题候选、文章和平台包生成。
- `scripts/knowledge_share.py`：指定主题研究模式。
- `scripts/generate_knowledge_share.ps1`：指定主题模式入口。
- `config/sources.json`：新闻和 RSS 来源配置。
- `prompts/`：日报、文章、平台版本和封面提示词。
- Tavily：指定主题搜索来源，密钥只放在本地 `.env`，不提交 Git。

### 运行记录和失败恢复

- `scripts/run_manifest.py`：保存 `run_id`、状态、阶段、失败信息和重试关系。
- 运行记录位于 `E:\社区账号\content-pipeline\out\YYYY-MM-DD\`。
- `scripts/retry_run.py` 和 `scripts/retry_run.ps1`：对失败运行进行受控重试。
- 失败信息只保存安全摘要，不保存密钥、Cookie 或登录态。

### 人工审核和 Worker

- `scripts/review_state.py`：文章审核状态和历史。
- `scripts/platform_review.py`：平台版本审核状态和历史。
- `scripts/worker_server.py`：提供以下本地接口：

```text
POST /review
POST /platform-review
POST /run-daily
POST /run-knowledge
POST /dryrun
GET  /health
```

### 平台版本和 DryRun

- `scripts/generate_platform_versions.py`：文章人工通过后生成平台版本。
- `scripts/render_platform_pack_html.py`：生成平台版本审核页面。
- `scripts/publish_daily.ps1`：调用浏览器辅助流程。
- `scripts/publish/common.ps1`：平台入口检查、字段读取、DryRun 记录和日志脱敏。
- `out/dryrun-latest.json`：最新 DryRun 记录。

DryRun 状态：`not_run` 尚未检查；`passed` 检查通过；`needs_manual` 需要处理登录、验证码、风控或入口；`failed` 脚本或页面检查失败。

### n8n 和 Docker

- `docker-compose.yml`：n8n、PostgreSQL、Redis 和 RSSHub 服务配置。
- `n8n-workflows/daily-tech-intel.json`：每日日报工作流定义。
- 当前工作流：`Schedule Trigger 19:10 → POST host.docker.internal:8020/run-daily → 校验 Worker 业务状态`。
- n8n 传递 `request_id`，Worker 返回对应的 `run_id` 和 manifest。
- Worker 通过并发锁避免同一时间重复执行日报。
- Docker 工作流更新后，需要重启 `content-n8n` 才能使激活状态生效。

### 封面

文章生成时会生成封面提示词，不会自动生成封面图片：

```text
E:\社区账号\content-pipeline\out\YYYY-MM-DD\cover-prompt-*.txt
```

提示词包含 16:9 通用横版和 3:4 小红书封面建议。

## 四、补充说明和安全边界

不要提交或公开：

```text
.env
browser-profiles
data/
local-files/
Cookie
Token
密码
私钥
真实账号登录态
```

`out/`、`site/` 和 `logs/` 主要是本地运行产物，是否提交以 `.gitignore` 和任务卡要求为准。

平台边界：当前不接入新的社交平台 API，不自动发布，不自动处理验证码、登录和风控，不通过脚本绕过平台权限，最终发布必须由用户手动确认。

日常排查顺序：检查 Docker 容器 → 检查 Worker `/health` → 查看 n8n Execution → 查看 `out/run-manifest-latest.json` → 查看文章审核页 → 查看平台审核页 → 最后检查浏览器插件和平台登录状态。

维护建议：先稳定运行一到两周，再根据真实失败记录创建新任务卡；修改代码前创建功能分支；修改后运行测试和最小本地验收；不要直接在 `main` 上开发；不要因为一次运行失败就删除运行记录；n8n 工作流更新后先手动执行，再等待每日定时运行。

## 五、项目最终原则

项目的目标不是“无人值守自动发帖”，而是：

> 自动完成信息收集和文章生产，把事实、来源、风险和平台内容交给人审核，再由人完成最终发布。
