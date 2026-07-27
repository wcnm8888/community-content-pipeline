# AGENTS.md

## 项目升级摘要（先看这里）

### 一、如何使用项目

项目目录：`E:\社区账号\content-pipeline`

启动 Docker 服务和本地 Worker：

```powershell
Set-Location "E:\社区账号\content-pipeline"
docker compose up -d
.\scripts\start_worker.ps1
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8020/health
```

主要入口：

```text
n8n 管理页：     http://localhost:5860
预览站点：       http://localhost:8010
Worker 健康检查：http://localhost:8020/health
日报工作流：     在 n8n 中执行 Daily Tech Intelligence
```

指定主题生成文章：

```powershell
.\scripts\generate_knowledge_share.ps1 `
  -Topic "好用的 Codex 插件分享" `
  -Angle "介绍使用场景、适合人群、配置方法和注意事项" `
  -TopResults 8 `
  -ReaderTimeout 18
```

查看和审核：

```text
日报草稿：     http://localhost:8010/draft-latest.html
主题文章：     http://localhost:8010/knowledge-share-latest.html
内容池：       http://localhost:8010/content-pool-latest.html
主题候选：     http://localhost:8010/topic-candidates-latest.html
文章人工审核： http://localhost:8010/article-review-latest.html
平台版本审核： http://localhost:8010/platform-pack-latest.html
```

审核顺序：文章和来源 → 文章人工通过 → 平台版本 → 平台人工通过 → 按需 DryRun → 原有插件同步 → 用户手动发布。

DryRun 命令：

```powershell
.\scripts\publish_daily.ps1 -Mode DryRun
```

DryRun 只检查入口、登录状态、验证码/风控和字段，不填写、不保存、不发布。

常用测试：

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
Get-ChildItem scripts -Filter *.py | ForEach-Object { python -m py_compile $_.FullName }
python -m json.tool n8n-workflows\daily-tech-intel.json > $null
```

### 二、项目整体流程和思想

```text
新闻或指定主题采集
→ 来源读取、去重和筛选
→ AI 生成文章草稿
→ 事实、来源和质量检查
→ 人工审核文章
→ 生成不同平台版本
→ 人工审核平台版本
→ 浏览器插件辅助同步
→ 人工最终确认发布
```

项目采用“自动生产、人工审核、人工发布”的半自动模式。生成和发布严格分离；AI 不直接发布；文章审核和平台版本审核相互独立；所有运行都保留来源、`run_id`、事实、审核和失败阶段记录；n8n 只负责调度，内容生产由脚本负责；同一时间只启用一个每日调度器。

### 三、具体如何实现

- `scripts/daily_digest.py`：日报采集、去重、事实卡、主题候选、文章和平台包生成。
- `scripts/knowledge_share.py`：指定主题研究，使用 Tavily 搜索和 Reader 获取来源正文。
- `scripts/run_manifest.py`：保存每次运行的状态、阶段、错误和重试关系。
- `scripts/review_state.py`、`scripts/platform_review.py`：文章和平台人工审核状态。
- `scripts/worker_server.py`：提供 `/run-daily`、`/run-knowledge`、`/review`、`/platform-review`、`/dryrun` 和 `/health` 接口。
- `scripts/generate_platform_versions.py`：文章人工通过后生成平台版本。
- `scripts/publish_daily.ps1` 与 `scripts/publish/`：使用浏览器辅助流程，只做 DryRun、草稿或人工确认后的同步。
- `n8n-workflows/daily-tech-intel.json`：19:10 触发日报，传递 `request_id`，接收 Worker 返回的 `run_id` 和 manifest，并校验业务状态。
- `prompts/cover-image.md`：生成封面提示词；当前只生成提示词，不自动生成图片。

### 四、其他补充

- 不要同时启用 n8n Schedule Trigger 和 Windows 计划任务 `ContentPipelineDailyDigest`。
- Docker 工作流更新后需要重启 `content-n8n`；Worker 代码更新后需要重启本地 Worker。
- `out/run-manifest-latest.json` 是最新运行清单；`out/dryrun-latest.json` 是最新平台 DryRun 记录。
- 发生问题时按“Docker → Worker /health → n8n Execution → run manifest → 审核页面 → 浏览器登录状态”的顺序排查。
- 先稳定运行一到两周，再根据真实失败记录创建下一张任务卡。


## 阅读方式

这份文档现在按“先看主流程，再查附录”的方式组织。

优先阅读：

```text
1. 项目总览
2. 每日技术情报日报链路
3. 知识分享文章生成链路
4. 两条链路共用能力
5. 常用命令和预览页面
```

后面的内容策略、信息源、平台发布、浏览器 profile、清理规则等，是维护和排障时再查的详细参考。

## 项目总览

项目目录：

```text
E:\社区账号\content-pipeline
```

这个项目是一个半自动内容生产系统，目前有两条互相独立、但共享底层能力的内容链路：

| 链路 | 入口 | 适合生成什么 | 最新正文文件 | 最新预览页 |
|---|---|---|---|---|
| 每日技术情报日报 | RSS / n8n / `/run-daily` | 每天一篇围绕近期技术变化的情报文章 | `out\draft-latest.md` | `site\draft-latest.html` |
| 知识分享文章 | 手动主题 / URL / `/run-knowledge` | 围绕知识点、技术主题、开源项目的解释型文章 | `out\knowledge-share-latest.md` | `site\knowledge-share-latest.html` |

两条链路共用：

```text
DeepSeek API
Jina Reader 正文提取
发布前审稿
平台发布字段包
封面提示词
本地 preview server
人工审核发布流程
```

注意：`article-review-latest.*` 和 `platform-pack-latest.*` 是共享 latest 文件，表示“最近一次生成内容”的审稿结果和平台字段包。最近运行的是日报，它们就对应日报；最近运行的是知识分享，它们就对应知识分享。

## 每日技术情报日报链路

### 目标

每日技术情报日报用于回答：

```text
今天技术圈最值得展开的一条变化是什么？
它为什么值得读者关心？
它对开发者、技术管理者、AI/Agent 创业者、安全和基础设施团队有什么行动价值？
```

它不是大杂烩日报，也不是把所有 RSS 都摘要一遍。系统会尽量每天只选择一个足够具体、足够有证据、对读者有行动价值的主线。

### 输入

日报链路的主要输入来自：

```text
config\sources.json 中配置的 RSS/Atom 信息源
config\sources.json 中的 profile / audience / focus
prompts\daily-tech-intel.md
prompts\platform-pack.md
prompts\cover-image.md
.env 中的 DeepSeek / Jina Reader 配置
```

### 工作流程

```text
n8n 定时触发或手动调用 /run-daily
-> scripts\daily_digest.py 抓取 RSS 信息源
-> 按来源权重、关键词、新鲜度、发布适配度、历史重复度打分
-> 生成今日内容池 content-pool-latest
-> 选择送入 Jina Reader 的候选来源
-> Jina Reader 提取网页正文
-> 生成事实卡片 fact-cards-latest
-> DeepSeek 生成选题候选 topic-candidates-latest
-> 选题闸门决定 FULL_ARTICLE / SINGLE_SOURCE_OBSERVATION / SHORT_OBSERVATION / NO_ARTICLE
-> DeepSeek 生成日报正文
-> 发布前审稿，必要时自动改写一次
-> 生成平台发布字段包 platform-pack-latest
-> 生成封面提示词
-> 渲染本地 HTML 预览页
-> 人工审核后发布
```

### 日报常用命令

完整本地生成：

```powershell
cd E:\社区账号\content-pipeline
python .\scripts\daily_digest.py --top 8 --limit-per-feed 5 --feed-timeout 12 --reader-timeout 18 --pool-size 30
python .\scripts\render_content_pool_html.py
python .\scripts\render_topic_candidates_html.py
python .\scripts\render_draft_html.py
python .\scripts\render_article_review_html.py
python .\scripts\render_platform_pack_html.py
```

通过 worker 触发：

```powershell
Invoke-WebRequest -UseBasicParsing -Method Post -Uri "http://localhost:8020/run-daily"
```

### 日报输出

```text
out\content-pool-latest.json / .md
out\fact-cards-latest.json / .md
out\topic-candidates-latest.json / .md
out\draft-latest.md
out\article-review-latest.json / .md
out\platform-pack-latest.json / .md
site\content-pool-latest.html
site\topic-candidates-latest.html
site\draft-latest.html
site\article-review-latest.html
site\platform-pack-latest.html
```

### 日报预览页

```text
今日内容池: http://localhost:8010/content-pool-latest.html
选题候选: http://localhost:8010/topic-candidates-latest.html
日报文章预览: http://localhost:8010/draft-latest.html
发布前审稿: http://localhost:8010/article-review-latest.html
平台发布字段包: http://localhost:8010/platform-pack-latest.html
```

## 知识分享文章生成链路

### 目标

知识分享链路用于回答：

```text
一个知识点到底是什么？
一个开源项目解决什么问题，适合谁，不适合谁？
一个工程概念如何用通俗、可执行、适合社交平台的方式讲清楚？
```

它不走 RSS 选题闸门，也不改动 `out\draft-latest.md` 和 `site\draft-latest.html`，因此不会破坏每日技术情报日报。

### 输入

知识分享链路的主要输入来自用户命令：

```text
--topic        必填，知识点、技术主题或开源项目名
--angle        可选，写作角度
--audience     可选，目标读者；不填则使用 config\sources.json profile audience
--urls         可选，一个或多个资料 URL
--top-results  可选，搜索结果数量，默认 8
--reader-timeout 可选，Jina Reader 超时时间，默认 18
```

典型例子：

```powershell
.\scripts\generate_knowledge_share.ps1 -Topic "MCP" -Angle "面向想接入 Agent 工具链的开发者" -Urls "https://modelcontextprotocol.io/"
```

这里的含义是：

```text
Topic = 写什么：MCP
Angle = 从什么角度写：面向想接入 Agent 工具链的开发者
Urls = 用哪些资料作为事实来源：https://modelcontextprotocol.io/
```

### 工作流程

```text
用户指定 --topic / --angle / --urls
-> scripts\generate_knowledge_share.ps1 整理参数
-> 调用 scripts\knowledge_share.py
-> 如果传了 --urls，优先使用手动资料链接
-> 如果没传 --urls，尝试使用 SEARCH_PROVIDER / TAVILY_API_KEY / TAVILY_BASE_URL 搜索
-> 合并搜索结果和手动 URL
-> 按来源类型、可信度、低质量特征过滤和排序
-> Jina Reader 提取网页正文
-> 生成结构化资料卡片
-> DeepSeek 根据知识分享提示词生成文章
-> 发布前审稿，必要时自动改写一次
-> 生成平台发布字段包和封面提示词
-> 渲染知识分享文章预览页
-> 人工审核后发布
```

### 资料来源策略

高优先级来源：

```text
官方文档
官方博客
GitHub README / Release / Issues
论文
权威工程实践文章
高质量技术博客
```

低优先级或需要过滤的来源：

```text
营销软文
榜单聚合
纯转载
无来源摘要
低质量 SEO 页面
```

系统不会长期保存网页全文，只保存：

```text
title
url
source_type
credibility_score
key_facts
useful_examples
cannot_infer
risk_notes
```

### 搜索 API 配置

如果要启用自动搜索，在本地 `.env` 中配置：

```env
SEARCH_PROVIDER=tavily
TAVILY_API_KEY=你的 Tavily API Key
TAVILY_BASE_URL=https://api.tavily.com/search
```

如果没有配置搜索 API，使用手动 URL 模式：

```powershell
python .\scripts\knowledge_share.py --topic "MCP" --urls "https://modelcontextprotocol.io/"
```

如果既没有搜索 API，也没有 `--urls`，脚本会报错并提示使用手动 URL 模式，不会静默失败。

### 知识分享常用命令

推荐的一键脚本：

```powershell
cd E:\社区账号\content-pipeline
.\scripts\generate_knowledge_share.ps1 -Topic "MCP" -Angle "面向想接入 Agent 工具链的开发者" -Urls "https://modelcontextprotocol.io/"
```

等价的 Python 命令：

```powershell
python .\scripts\knowledge_share.py --topic "MCP" --angle "面向想接入 Agent 工具链的开发者" --urls "https://modelcontextprotocol.io/"
python .\scripts\render_knowledge_share_html.py
python .\scripts\render_article_review_html.py
python .\scripts\render_platform_pack_html.py
```

通过 worker 触发：

```powershell
$body = @{
  topic = "MCP"
  angle = "给开发者的工程化入门"
  urls = @("https://modelcontextprotocol.io/")
} | ConvertTo-Json -Depth 4

Invoke-WebRequest `
  -UseBasicParsing `
  -Method Post `
  -Uri "http://localhost:8020/run-knowledge" `
  -ContentType "application/json; charset=utf-8" `
  -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

如果 `/run-knowledge` 返回 `not found`，通常说明端口 `8020` 上运行的是旧 worker。关闭旧 worker 窗口或 Ctrl+C 后重新运行：

```powershell
.\scripts\start_worker.ps1
```

### 知识分享输出

```text
out\YYYY-MM-DD\knowledge-share-时间.md
out\YYYY-MM-DD\knowledge-share-时间.json
out\knowledge-share-latest.md
out\knowledge-share-latest.json
site\knowledge-share-latest.html
out\article-review-latest.json / .md
out\platform-pack-latest.json / .md
out\YYYY-MM-DD\cover-prompt-时间.txt
```

### 知识分享预览页

```text
知识分享文章预览: http://localhost:8010/knowledge-share-latest.html
发布前审稿: http://localhost:8010/article-review-latest.html
平台发布字段包: http://localhost:8010/platform-pack-latest.html
```

## DeepSeek 调用与提示词

### 共用调用方式

两条链路都通过 `scripts\daily_digest.py` 中的 `deepseek_chat()` 调 DeepSeek。请求体是 OpenAI-compatible 格式：

```json
{
  "model": "DEEPSEEK_MODEL",
  "messages": [
    {"role": "system", "content": "系统提示词"},
    {"role": "user", "content": "用户提示词"}
  ],
  "stream": false
}
```

配置来自 `.env`：

```env
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_API_KEY=你的 DeepSeek API Key
```

脚本不会输出真实 API Key。

### 日报生成提示词

日报正文生成使用：

```text
system prompt: prompts\daily-tech-intel.md
user prompt: scripts\daily_digest.py 中 build_article_prompt() 动态生成
```

user prompt 会包含：

```text
账号定位
目标读者
重点方向
今日内容池摘要
选题闸门通过的候选
写作模式
事实卡片
候选素材正文摘录
```

### 知识分享生成提示词

知识分享正文生成使用：

```text
system prompt: prompts\knowledge-share.md
user prompt: scripts\knowledge_share.py 中 build_knowledge_prompt() 动态生成
```

`prompts\knowledge-share.md` 的核心要求：

```text
你是“知识分享文章”的中文主编。
文章要更吸引读者、更通俗、结构清楚，但不能洗稿，不能编造事实。
所有关键判断必须来自资料卡片和来源摘录，最后保留来源链接。
开头必须从具体场景、痛点、反常识问题或读者熟悉的困惑切入。
复杂概念采用“一句话解释，再拆 3 个关键点，再给一个小例子”的结构。
正文必须从一级标题 # 标题 开始。
```

动态 user prompt 结构：

```text
请基于资料卡片和来源摘录，写一篇中文知识分享文章。

主题：{topic}
写作角度：{angle}
目标读者：{audience}

资料卡片：
{cards_text}

来源证据摘录：
{evidence}

硬性要求：
- 正文必须从一级标题 `# 标题` 开始。
- 开头不要铺背景，直接用具体场景、痛点、反常识问题或读者熟悉的困惑切入。
- 先回答“为什么读者要关心”，再解释概念。
- 如果是开源项目，写清它解决什么问题、适合谁、不适合谁、核心能力、上手方式、风险边界、可替代方案。
- 如果是知识点，写清它是什么、为什么出现、解决什么问题、常见误区、实践建议、延伸阅读。
- 复杂概念要用“一句话解释 + 3 个关键点 + 一个小例子”的方式讲。
- 不要洗稿，不要逐段改写任一来源。
- 不要新增来源中没有的事实、数字、日期、性能结论或项目能力。
- 保留“来源链接”章节，只能使用资料卡片中的 URL。
```

知识分享不是直接把网页全文丢给模型。它会先把资料转成卡片和证据摘录，再把这些结构化材料交给 DeepSeek，所以更容易控制事实边界。

## 两条链路共用能力

### 发布前审稿

日报和知识分享都会生成 `article-review-latest.json/md`。审稿会检查：

```text
标题是否夸张
是否有事实边界问题
是否出现相对日期
是否有推测 URL
是否编造来源中没有的数字、日期、模型名、benchmark、能力边界
是否适合同步到各平台
```

如果审稿认为需要修改，系统会自动改写一次。改写仍必须基于原始来源证据，不允许新增事实。

### 平台发布字段包

日报和知识分享都会生成 `platform-pack-latest.json/md`，并渲染：

```text
http://localhost:8010/platform-pack-latest.html
```

覆盖平台：

```text
知乎
稀土掘金
CSDN
抖音
小红书
B站
```

字段规则来自：

```text
config\platforms.json
prompts\platform-pack.md
```

### 封面提示词

两条链路都会用 `prompts\cover-image.md` 生成封面提示词：

```text
out\YYYY-MM-DD\cover-prompt-时间.txt
```

## 常用服务和页面

启动 worker：

```powershell
cd E:\社区账号\content-pipeline
.\scripts\start_worker.ps1
```

启动预览服务：

```powershell
cd E:\社区账号\content-pipeline
.\scripts\start_preview_server.ps1
```

健康检查：

```powershell
Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8020/health"
```

常用页面：

```text
今日内容池: http://localhost:8010/content-pool-latest.html
选题候选: http://localhost:8010/topic-candidates-latest.html
日报文章预览: http://localhost:8010/draft-latest.html
知识分享文章预览: http://localhost:8010/knowledge-share-latest.html
发布前审稿: http://localhost:8010/article-review-latest.html
平台发布字段包: http://localhost:8010/platform-pack-latest.html
```

## 安全和隐私边界

必须遵守：

```text
不读取或输出 .env 中的真实密钥
不保存搜索结果网页全文到长期日志
不自动发布到平台
不绕过验证码或账号安全限制
不批量删除 out / site / logs / 配置文件
不重置仓库或覆盖用户未要求处理的文件
生产配置和密钥只做必要存在性检查，不展示内容
```

涉及发布、付款、账号安全、隐私授权、批量删除、重置、清理、覆盖等动作时，必须先说明风险并等待用户确认。

## 详细参考

下面保留原有详细说明，包含内容策略、信息源、自动化发文 profile、常见问题、清理规则、后续方向和质量原则。日常使用优先看上面的两条链路说明；维护项目时再查下面的细节。

## 项目定位

这是一个半自动“技术情报日报”内容生产系统，用于每天生成一篇适合国内社交平台发布的中文技术情报文章。

重点内容方向：

- AI / Agent / LLM 应用开发
- AI coding / vibe coding / coding agent / AI IDE
- AI workflow / workflow automation / Agent 工作流
- MCP / RAG / tool use / computer use / eval / benchmark
- 有价值的开源项目
- 开发者工具
- 计算机科学与工程实践
- 网络工程、云计算、基础设施
- 网络安全、漏洞、攻防趋势

系统优先采集国外一手信息源和高质量技术社区内容，但文章表达中不要强调“海外”或“对国内读者”。统一使用：

```text
技术情报日报
意义
```

避免使用：

```text
海外技术情报日报
对国内读者的意义
```

## 当前架构

整体链路：

```text
n8n 定时触发
-> 本机 content worker
-> 抓取技术 RSS 信息源
-> 生成今日内容池与 RSS 初筛建议主线
-> Jina Reader 提取网页正文
-> DeepSeek 生成中文技术情报文章
-> 生成各平台发布字段包
-> 生成封面提示词
-> 渲染成本地 HTML 文章页
-> Wechatsync 同步到各平台草稿箱
-> 人工审核发布
```

新增的“知识分享文章生成”链路与每日 RSS 日报并行存在，不替代日报：

```text
用户指定知识点 / 技术主题 / 开源项目名
-> 可选调用 Tavily Search API 搜索高质量资料
-> 或使用用户手动传入的 --urls 资料链接
-> 按来源类型和可信度过滤、排序、去重
-> Jina Reader 提取网页正文
-> 生成结构化资料卡片
-> DeepSeek 按“知识分享主编”提示词生成中文文章
-> 复用发布前审稿，必要时自动改写一次
-> 复用平台发布字段包和封面提示词
-> 渲染知识分享文章预览页
-> 人工审核发布
```

知识分享链路适合写“一个知识点怎么理解”“一个开源项目适合谁”“某个工程概念怎么上手”。日报链路适合写“今天 RSS 信息源里最值得关注的一条技术变化”。两者共享 DeepSeek、Jina Reader、审稿、平台字段包和封面提示词，但正文 latest 文件分开，避免知识分享文章覆盖日报语义。

组件职责：

| 组件 | 作用 |
|---|---|
| n8n | 定时触发任务，每天晚上调用 worker |
| RSSHub | 扩展可采集的信息源 |
| content worker | 本机 Python 服务，负责采集、生成、渲染 |
| 今日内容池 | RSS 抓取后的结构化候选池，展示候选文章、分数拆解、领域信号和主线建议 |
| Jina Reader | 将网页正文转换成 Markdown |
| DeepSeek API | 负责筛选、总结、成文 |
| Wechatsync | 同步到公众号、知乎、头条、小红书等平台草稿箱 |
| 人工审核 | 检查事实、排版、封面、平台风险后发布 |

## 关键地址

```text
n8n: http://localhost:5860
今日内容池: http://localhost:8010/content-pool-latest.html
选题候选: http://localhost:8010/topic-candidates-latest.html
最新文章预览: http://localhost:8010/draft-latest.html
知识分享文章预览: http://localhost:8010/knowledge-share-latest.html
发布前审稿: http://localhost:8010/article-review-latest.html
平台发布字段包: http://localhost:8010/platform-pack-latest.html
worker 健康检查: http://localhost:8020/health
n8n 容器调用 worker: http://host.docker.internal:8020/run-daily
本机触发知识分享: http://localhost:8020/run-knowledge
```

说明：n8n 运行在 Docker 容器里，容器中的 `localhost` 指向容器自身。要访问 Windows 主机上的 worker，必须使用 `host.docker.internal`。

## 重要目录和文件

项目根目录：

```text
E:\社区账号\content-pipeline
```

核心文件：

```text
docker-compose.yml
.env
.env.example
README.md
AGENTS.md
PLAYWRIGHT-AUTO-PUBLISH-PLAN.md
```

配置和提示词：

```text
config\sources.json
prompts\daily-tech-intel.md
prompts\knowledge-share.md
prompts\cover-image.md
prompts\platform-pack.md
```

n8n 工作流：

```text
n8n-workflows\daily-tech-intel.json
```

脚本：

```text
scripts\daily_digest.py
scripts\knowledge_share.py
scripts\worker_server.py
scripts\render_content_pool_html.py
scripts\render_topic_candidates_html.py
scripts\render_draft_html.py
scripts\render_knowledge_share_html.py
scripts\render_article_review_html.py
scripts\render_platform_pack_html.py
scripts\generate_knowledge_share.ps1
scripts\start_worker.ps1
scripts\start_preview_server.ps1
```

输出目录：

```text
out
site
```

## 日常使用

每天使用前需要启动两类东西：

1. Docker 里的 n8n / RSSHub / 数据库等容器。
2. Windows 本机的 Python content worker 和静态预览服务。

注意：新增的“今日内容池”“选题候选”“发布前审稿”和“知识分享文章预览”不需要额外启动第三个常驻服务。它们使用同一个 worker 和同一个 preview server。每日 RSS 日报由 `/run-daily` 触发；知识分享文章由 `knowledge_share.py`、`generate_knowledge_share.ps1` 或 `/run-knowledge` 触发。

n8n 定时触发后，会调用本机 worker。worker 会完成：

~~~
接收 n8n 请求
抓取 RSS 信息源
生成今日内容池和主线选择依据
调用 Jina Reader 提取正文
生成事实卡片
生成选题候选并执行发布闸门
调用 DeepSeek 生成文章
执行发布前审稿，必要时自动改写一次
生成平台发布字段包
生成封面提示词
渲染四个本地预览页面（http://localhost:8010）
~~~

每天电脑开机后，进入项目目录，启动这两个本机服务即可：

~~~
cd E:\社区账号\content-pipeline
.\scripts\start_worker.ps1
.\scripts\start_preview_server.ps1
~~~

两个服务的作用：

| 服务 | 启动命令 | 作用 |
|---|---|---|
| content worker | `.\scripts\start_worker.ps1` | 监听 `http://localhost:8020`，接收 n8n 请求，执行 RSS 抓取、内容池生成、事实卡片、选题候选、文章生成、发布前审稿、平台字段包生成和 HTML 渲染 |
| preview server | `.\scripts\start_preview_server.ps1` | 监听 `http://localhost:8010`，展示今日内容池、选题候选、文章预览、发布前审稿和平台字段包 |

启动后可检查：

```powershell
Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8020/health"
Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8010/content-pool-latest.html"
Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8010/topic-candidates-latest.html"
Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8010/draft-latest.html"
Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8010/knowledge-share-latest.html"
Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8010/article-review-latest.html"
Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8010/platform-pack-latest.html"
```

如果只打开旧页面但没有运行生成，页面会显示上一次生成的结果；新的内容池和日报文章会在 n8n 定时执行或手动执行日报工作流后刷新，知识分享文章会在手动运行知识分享链路或调用 `/run-knowledge` 后刷新。



每天晚上 7 点到 10 点之间保持电脑打开。n8n 工作流默认每天：

```text
19:10
```

自动运行。

日常流程：

1. 打开今日内容池：

```text
http://localhost:8010/content-pool-latest.html
```

先看 RSS 初筛建议主线、领域信号排行和入选成文候选，判断今天是否应该采用该主题，或是否需要人工调整选题。

2. 打开选题候选页：

```text
http://localhost:8010/topic-candidates-latest.html
```

重点看“总体决策”“闸门”和“写作模式”：

- `WRITE` + `FULL_ARTICLE`：有 A/B 级候选且多来源能支撑同一主线，可以进入完整主文。
- `WRITE` + `SINGLE_SOURCE_OBSERVATION`：有一个值得写的强来源，但支撑来源不足两个；系统会生成谨慎的单来源观察，不能写成行业定论。
- `WRITE_SHORT` + `SHORT_OBSERVATION`：没有强主线，但有 C 级可写信号；系统会生成短观察，适合轻量发布或作为当天补位内容。
- `REJECT` + `NO_ARTICLE`：没有可用候选，不建议同步正文；系统会生成“今日无强主线”的说明。

日更策略：不要把“没有强主线”直接等同于“今天没有内容”。优先使用 `FULL_ARTICLE`；没有强主线时，用 `SINGLE_SOURCE_OBSERVATION` 或 `SHORT_OBSERVATION` 维持发布节奏，但正文必须主动降低语气，避免把单一实验、论文或弱信号包装成大趋势。

3. 打开最新文章页：

```text
http://localhost:8010/draft-latest.html
```

4. 打开发送前审稿页：

```text
http://localhost:8010/article-review-latest.html
```

重点看质量分、是否建议同步、是否已自动改写，以及是否还有标题夸张、事实边界、相对日期、来源链接等问题。

5. 打开平台发布字段包：

```text
http://localhost:8010/platform-pack-latest.html
```

如果选题闸门或发布前审稿未通过，平台字段包会显示“不建议发布”，不要复制到平台。

6. 检查文章：

```text
今日主线是否和内容池信号一致
今日主线是否来自选题候选页通过的 A/B 级候选
标题是否具体
主线是否清楚
事实是否可靠
来源链接是否保留
表达是否夸张
是否适合当天发布
```

7. 用 Wechatsync 同步到各平台草稿箱。

8. 在平台后台检查，并从平台字段包复制对应内容：

```text
排版
封面
标题
摘要
链接
敏感词
AI 辅助内容标识需求
```

9. 封面的提示词：

~~~
E:\社区账号\content-pipeline\out\YYYY-MM-DD\cover-prompt-时间.txt
~~~

10. 人工确认后发布。

## 知识分享文章生成

知识分享链路用于“用户先指定主题，再生成一篇解释型文章”。它不走 RSS 选题闸门，也不改动 `draft-latest.md` 和 `site\draft-latest.html`，因此不会破坏每日技术情报日报。

适合使用的场景：

```text
解释一个知识点：MCP、RAG、向量数据库、AI eval、prompt injection
介绍一个开源项目：LangGraph、n8n、Qdrant、LlamaIndex、Aider
写工程化入门：如何接入 Agent 工具链、如何做 RAG 评估、如何设计工具权限边界
```

完整工作方式：

```text
1. 用户传入 --topic，必要时补充 --angle 和 --audience。
2. 如果传了 --urls，系统把这些 URL 当作手动资料源。
3. 如果没有传 --urls，系统会尝试读取 SEARCH_PROVIDER / TAVILY_API_KEY / TAVILY_BASE_URL，当前支持 Tavily Search API。
4. 搜索结果和手动 URL 会合并、去重，并按来源类型打分。
5. 高优先级来源包括官方文档、官方博客、GitHub README/Release/Issues、论文、权威工程博客。
6. 低质量来源如营销软文、榜单聚合、纯转载、无来源摘要会被降权或过滤。
7. 对入选 URL 调用 Jina Reader 提取正文。
8. 系统只保存资料卡片、关键事实、可用例子、不可推断内容、风险提示和来源链接，不长期保存网页全文。
9. DeepSeek 按 prompts\knowledge-share.md 生成中文知识分享文章。
10. 文章继续走发布前审稿；如果发现事实边界、夸张标题、相对日期等问题，会自动改写一次。
11. 最后生成平台发布字段包、封面提示词和 HTML 预览页。
```

手动 URL 模式最稳，适合已经知道官方资料地址时使用：

```powershell
cd E:\社区账号\content-pipeline
python .\scripts\knowledge_share.py --topic "MCP" --angle "给开发者的工程化入门" --urls "https://modelcontextprotocol.io/"
python .\scripts\render_knowledge_share_html.py
python .\scripts\render_article_review_html.py
python .\scripts\render_platform_pack_html.py
```

也可以用封装脚本：

```powershell
cd E:\社区账号\content-pipeline
.\scripts\generate_knowledge_share.ps1 -Topic "MCP" -Angle "面向想接入 Agent 工具链的开发者" -Urls "https://modelcontextprotocol.io/"
```

如果要启用自动搜索，在本地 `.env` 中配置：

```env
SEARCH_PROVIDER=tavily
TAVILY_API_KEY=你的 Tavily API Key
TAVILY_BASE_URL=https://api.tavily.com/search
```

配置搜索 API 后，可以只给主题：

```powershell
python .\scripts\knowledge_share.py --topic "MCP" --angle "给开发者的工程化入门"
```

如果没有配置搜索 API，也没有传 `--urls`，脚本会直接报错并提示使用手动 URL 模式，不会静默失败。

知识分享预览页：

```text
http://localhost:8010/knowledge-share-latest.html
```

审稿和平台字段包仍然共用最新文件：

```text
http://localhost:8010/article-review-latest.html
http://localhost:8010/platform-pack-latest.html
```

注意：`article-review-latest.*` 和 `platform-pack-latest.*` 表示“最近一次生成内容”的审稿和平台字段包。最近运行的是日报，它们就对应日报；最近运行的是知识分享，它们就对应知识分享。

worker 接口也支持知识分享。重启 worker 后可调用：

```powershell
$body = @{
  topic = "MCP"
  angle = "给开发者的工程化入门"
  urls = @("https://modelcontextprotocol.io/")
} | ConvertTo-Json -Depth 4

Invoke-WebRequest `
  -UseBasicParsing `
  -Method Post `
  -Uri "http://localhost:8020/run-knowledge" `
  -ContentType "application/json; charset=utf-8" `
  -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

返回结果里应包含：

```text
knowledge_share_url
preview_url
article_review_url
platform_pack_url
```

## 手动重新生成

在 n8n 中打开：

```text
Daily Tech Intelligence / 技术情报日报
```

点击：

```text
Execute workflow / 执行工作流程
```

执行成功后刷新：

```text
http://localhost:8010/content-pool-latest.html
http://localhost:8010/topic-candidates-latest.html
http://localhost:8010/draft-latest.html
http://localhost:8010/article-review-latest.html
http://localhost:8010/platform-pack-latest.html
```

必要时手动启动本机服务：

```powershell
cd E:\社区账号\content-pipeline
.\scripts\start_worker.ps1
.\scripts\start_preview_server.ps1
```

## 测试新工作流

### 1. 只测试 RSS 和今日内容池

这个测试不会调用 DeepSeek，不会生成新文章，适合先检查新增信息源、选题池和 HTML 预览是否正常。

```powershell
cd E:\社区账号\content-pipeline
python -c "import json, time; from pathlib import Path; from scripts.daily_digest import collect_items, write_content_pool; config=json.loads(Path('config/sources.json').read_text(encoding='utf-8')); items=collect_items(config, 5, 8); ts=time.strftime('%Y%m%d-%H%M%S'); run_dir=Path('out')/time.strftime('%Y-%m-%d'); run_dir.mkdir(parents=True, exist_ok=True); payload, jp, mp, latest=write_content_pool(items, items[:8], ts, run_dir, 30); print('collected', len(items)); print('recommended', (payload.get('recommended_topic') or {}).get('category')); print(jp); print(latest)"
python .\scripts\render_content_pool_html.py
```

检查：

```text
http://localhost:8010/content-pool-latest.html
```

如果预览服务未启动，先运行：

```powershell
.\scripts\start_preview_server.ps1
```

### 2. 测试完整本地生成链路

这个测试会调用 Jina Reader 和 DeepSeek，并生成文章、内容池、封面提示词、平台发布字段包。

```powershell
cd E:\社区账号\content-pipeline
python .\scripts\daily_digest.py --top 8 --limit-per-feed 5 --feed-timeout 12 --reader-timeout 18 --pool-size 30
python .\scripts\render_content_pool_html.py
python .\scripts\render_topic_candidates_html.py
python .\scripts\render_draft_html.py
python .\scripts\render_article_review_html.py
python .\scripts\render_platform_pack_html.py
```

检查三个页面：

```text
http://localhost:8010/content-pool-latest.html
http://localhost:8010/topic-candidates-latest.html
http://localhost:8010/draft-latest.html
http://localhost:8010/article-review-latest.html
http://localhost:8010/platform-pack-latest.html
```

### 3. 测试 worker 接口

确认本机 worker 已启动：

```powershell
cd E:\社区账号\content-pipeline
.\scripts\start_worker.ps1
```

健康检查：

```powershell
Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8020/health"
```

触发完整日报工作流：

```powershell
Invoke-WebRequest -UseBasicParsing -Method Post -Uri "http://localhost:8020/run-daily"
```

返回结果里应包含：

```text
content_pool_url
topic_candidates_url
preview_url
article_review_url
platform_pack_url
```

### 4. 测试知识分享链路

手动 URL 模式会调用 Jina Reader 和 DeepSeek，并生成知识分享文章、发布前审稿、封面提示词和平台发布字段包：

```powershell
cd E:\社区账号\content-pipeline
python .\scripts\knowledge_share.py --topic "MCP" --angle "给开发者的工程化入门" --urls "https://modelcontextprotocol.io/"
python .\scripts\render_knowledge_share_html.py
python .\scripts\render_article_review_html.py
python .\scripts\render_platform_pack_html.py
```

检查页面：

```text
http://localhost:8010/knowledge-share-latest.html
http://localhost:8010/article-review-latest.html
http://localhost:8010/platform-pack-latest.html
```

测试搜索未配置时的错误提示：

```powershell
python .\scripts\knowledge_share.py --topic "MCP" --top-results 1
```

如果 `.env` 没有配置搜索 API，这条命令应清晰提示配置搜索或使用 `--urls`，而不是静默失败。

测试 worker 知识分享接口：

```powershell
$body = @{
  topic = "MCP"
  angle = "给开发者的工程化入门"
  urls = @("https://modelcontextprotocol.io/")
} | ConvertTo-Json -Depth 4

Invoke-WebRequest `
  -UseBasicParsing `
  -Method Post `
  -Uri "http://localhost:8020/run-knowledge" `
  -ContentType "application/json; charset=utf-8" `
  -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

如果返回 `not found`，通常说明端口 `8020` 上运行的是旧 worker，需要关闭旧窗口或 Ctrl+C 后重新运行：

```powershell
.\scripts\start_worker.ps1
```

### 5. 通过 n8n 测试

启动 Docker 后，在 n8n 打开：

```text
Daily Tech Intelligence / 技术情报日报
```

点击：

```text
Execute workflow / 执行工作流程
```

执行完成后依次检查：

```text
http://localhost:8010/content-pool-latest.html
http://localhost:8010/topic-candidates-latest.html
http://localhost:8010/draft-latest.html
http://localhost:8010/article-review-latest.html
http://localhost:8010/platform-pack-latest.html
```

## 生成结果

`out` 目录中的常见文件：

| 文件 | 作用 |
|---|---|
| `YYYY-MM-DD\content-pool-时间.json` | 某次 RSS 后生成的今日内容池 JSON，包含候选文章、分数拆解、领域信号和主线建议 |
| `YYYY-MM-DD\content-pool-时间.md` | 某次 RSS 后生成的今日内容池 Markdown |
| `content-pool-latest.json` | 最新今日内容池 JSON |
| `content-pool-latest.md` | 最新今日内容池 Markdown |
| `YYYY-MM-DD\fact-cards-时间.json` | 某次生成的事实卡片 JSON，包含每个来源可用事实、需核对数字和不可推断内容 |
| `YYYY-MM-DD\fact-cards-时间.md` | 某次生成的事实卡片 Markdown |
| `fact-cards-latest.json` | 最新事实卡片 JSON |
| `fact-cards-latest.md` | 最新事实卡片 Markdown |
| `YYYY-MM-DD\topic-candidates-时间.json` | 某次生成的选题候选 JSON，包含 A/B/C/REJECT 等级和发布闸门 |
| `YYYY-MM-DD\topic-candidates-时间.md` | 某次生成的选题候选 Markdown |
| `topic-candidates-latest.json` | 最新选题候选 JSON |
| `topic-candidates-latest.md` | 最新选题候选 Markdown |
| `YYYY-MM-DD\daily-digest-时间.md` | 某次生成的日报 Markdown |
| `draft-latest.md` | 最新日报固定文件 |
| `YYYY-MM-DD\knowledge-share-时间.json` | 某次生成的知识分享资料卡片和元数据 JSON |
| `YYYY-MM-DD\knowledge-share-时间.md` | 某次生成的知识分享文章 Markdown |
| `knowledge-share-latest.json` | 最新知识分享资料卡片和元数据 JSON |
| `knowledge-share-latest.md` | 最新知识分享文章 Markdown |
| `YYYY-MM-DD\article-review-时间.json` | 某次发布前审稿 JSON，包含质量分、问题清单、是否建议同步 |
| `YYYY-MM-DD\article-review-时间.md` | 某次发布前审稿 Markdown |
| `article-review-latest.json` | 最新发布前审稿 JSON |
| `article-review-latest.md` | 最新发布前审稿 Markdown |
| `YYYY-MM-DD\cover-prompt-时间.txt` | 某次生成的封面图提示词 |
| `YYYY-MM-DD\platform-pack-时间.json` | 某次生成的平台发布字段包 |
| `YYYY-MM-DD\platform-pack-时间.md` | 某次生成的平台发布字段包 Markdown |
| `platform-pack-latest.json` | 最新平台发布字段包 JSON |
| `platform-pack-latest.md` | 最新平台发布字段包 Markdown |

`site\content-pool-latest.html` 是最新今日内容池网页预览，对应：

```text
http://localhost:8010/content-pool-latest.html
```

`site\topic-candidates-latest.html` 是最新选题候选网页预览，对应：

```text
http://localhost:8010/topic-candidates-latest.html
```

`site\draft-latest.html` 是最新文章网页预览，对应：

```text
http://localhost:8010/draft-latest.html
```

`site\knowledge-share-latest.html` 是最新知识分享文章网页预览，对应：

```text
http://localhost:8010/knowledge-share-latest.html
```

`site\article-review-latest.html` 是最新发布前审稿网页预览，对应：

```text
http://localhost:8010/article-review-latest.html
```

`site\platform-pack-latest.html` 是最新平台字段包网页预览，对应：

```text
http://localhost:8010/platform-pack-latest.html
```

## 平台发布字段

平台规则配置：

```text
config\platforms.json
```

当前覆盖：

| 平台 | 自动生成字段 |
|---|---|
| 知乎 | 标题、话题、摘要、16:9 封面、创作声明：包含 AI 辅助创作 |
| 稀土掘金 | 分类固定人工智能、标签、100 字内摘要、16:9 封面 |
| B站 | 标题、1 个话题、16:9 自定义封面、创作声明：AI 辅助创作声明 |
| CSDN | 标题、文章标签、256 字内摘要、16:9 封面、创作声明：部分由 AI 辅助生成 |
| 抖音 | 30 字内标题、30 字内摘要、话题、3:4 封面 |
| 小红书 | 20 字内标题、话题、3:4 封面、内容类型声明：笔记包含 AI 合成内容 |

## 自动化发文浏览器 Profile

Playwright 默认打开的是隔离的新浏览器环境，不会带日常 Chrome 的登录态。自动化发文必须使用发布专用 profile：

```text
E:\社区账号\browser-profiles\publish
```

自动化发文脚本制作规划见：

```text
PLAYWRIGHT-AUTO-PUBLISH-PLAN.md
```

当前规划中微博、公众号、今日头条不再发布，不创建这些平台的发布模块。

初始化：

```powershell
New-Item -ItemType Directory -Force "E:\社区账号\browser-profiles\publish"
playwright-cli -s=publish open --browser=chrome --profile="E:\社区账号\browser-profiles\publish"
```

第一次打开后，在这个浏览器里手动登录知乎、稀土掘金、B站、CSDN、抖音、小红书。后续自动化脚本固定使用：

```powershell
playwright-cli -s=publish goto "目标平台发布页"
```

不要执行：

```powershell
playwright-cli -s=publish delete-data
```

不要更换 `--profile` 路径；路径一换就是新的浏览器用户目录。遇到验证码或二次验证时，脚本应暂停并等待人工处理。

## 内容策略

当前策略是“每日单主线技术情报”，不是大杂烩日报。目标不是每天凑一篇，而是每天判断：今天有没有一个足够具体、足够有证据、对读者有行动价值的技术变化。

生成时应遵循：

```text
先选一个最值得写的主线问题
只围绕这个主线展开
不用平均覆盖所有领域
无关领域宁可不写
弱信号降级为短观察
没有可信主线就不发布主文
```

### 优先主题池

内容池应优先覆盖这些更容易产出高质量文章的主题：

```text
AI coding / vibe coding：
coding agent、AI IDE、Copilot/Cody、代码生成工作流、人机协作开发、从 prompt 到 repo 的开发流程变化

AI workflow / Agent workflow：
workflow automation、multi-agent orchestration、n8n/Zapier 类自动化、Agent 接入业务流程、人工审批与自动化边界

AI 工程化：
MCP、tool use、computer use、browser use、RAG、向量检索、eval/benchmark、模型部署、成本、观测、权限与安全边界

开发者工具与基础设施：
CI/CD、云原生、数据库、运行时、框架、可观测性、沙箱、DevEx、开源项目

安全与风险：
真实攻击事件、主动利用漏洞、供应链安全、AI 安全、prompt injection、权限隔离、数据泄露和防护实践

研究到应用：
论文、benchmark、新模型能力、开源实现，但必须说明它离真实工程使用还有多远
```

选题时不要因为 AI 更热门就自动选 AI。AI 题同样必须有具体变化、可验证事实和读者行动价值。

### 高质量选题标准

一个题进入 `FULL_ARTICLE`，至少应满足以下 3 项：

```text
有明确变化：新发布、真实案例、架构调整、能力边界变化、生态趋势或风险升级
有行动价值：读者看完能调整工具、流程、架构、风控或学习路线
有问题意识：能回答一个具体问题，而不是复述新闻
有证据支撑：标题、开头和核心判断都能被来源直接支持
有冲突或反差：新工具改变旧工作流，能力提升但工程约束变强，收益与风险同时出现
有时效性：近期发生，或虽然不是当天发生但今天出现了新的解释价值
```

低质量选题特征：

```text
只有单个产品 changelog，且没有明显影响
只有社区热帖，没有一手来源
只有单方声称、未经证实传闻或 contributed piece 中的二手描述
只有论文标题，没有可解释的工程意义
多个来源只是同一天出现，不能支撑同一主线
标题能写得很热闹，但正文只能泛泛而谈
需要靠猜测趋势、补充外部事实或制造焦虑才能成文
```

### 选题分层

当前“今天选什么题”的判断分三层：

```text
RSS 阶段：生成今日内容池，给出结构化信号和初筛建议
选题候选阶段：基于事实卡片判断 A/B/C/REJECT，并给出写作模式
人工阶段：检查主线是否成立，必要时重新生成、改为短观察或不发布
```

写作模式解释：

```text
FULL_ARTICLE：
至少 2 个强相关来源支撑同一主线，可以写 1200-1800 字主文。

SINGLE_SOURCE_OBSERVATION：
只有 1 个强来源，或旁证不足。只能写 800-1200 字谨慎观察，不能写成行业定论。

SHORT_OBSERVATION：
只有 C 级信号。写 500-900 字短观察，用于轻量发布或补位，不包装成深度主文。

NO_ARTICLE：
没有可信主线。宁可不发主文，也不要用弱素材硬凑。
```

### 内容池筛选机制

内容池筛选发生在 `scripts\daily_digest.py` 的 RSS 抓取之后、Jina Reader 正文提取之前。

具体顺序是：

```text
collect_items：抓取 RSS，按 URL 去重，计算单篇 RSS 分和发布适配分
load_recent_history / apply_history_penalties：读取最近 7 天历史内容池和文章标题，计算历史降权
final_rank_score：用 RSS 分、发布适配分和历史降权重新排序
select_items_for_article：从排序后的内容池中选出送入 Jina Reader 和 DeepSeek 的成文候选
write_content_pool：把完整内容池、领域信号、初筛建议主线和入选候选写入 out 与 site 预览
```

RSS 阶段的单篇分数：

```text
单篇分数 = 信息源权重 * 4 + 新鲜度分 + 关键词命中数 * 8
```

新鲜度分：

```text
36 小时内 +35
96 小时内 +20
168 小时内 +10
更早或未知 +0
```

领域信号：

```text
领域信号 = 同领域 Top 5 最终排序分累加 + min(同领域数量, 5) * 8
```

注意：分数只用于 RSS 初筛和解释“为什么这些题进入今天的候选池”，不是事实判断，也不是自动发布依据。

现在内容池还会额外标注：

```text
信息类型：
ai_coding_workflow / ai_workflow / ai_engineering / security_research / engineering_practice / product_release / research / open_source / community_analysis / maintenance_notice

发布适配分：
信息类型基准分 + 读者相关性 + 行动价值 + 新知识密度 - 叙事风险扣分

风险提醒：
例如“维护性通知不能写成重大事故”“未见主动利用证据，不能暗示攻击爆发”“单来源只能写观察，不能写趋势定论”
```

最终排序分：

```text
最终排序分 = 单篇分数 * 0.45 + 发布适配分 * 1.4 - 历史降权
```

历史降权规则：

```text
最近 7 天出现过同一链接：重度降权，通常不再作为今日主线
标题与近期内容高度相似：中到重度降权
同一领域最近多次成为建议主线：领域冷却降权
同一领域近期入选素材过多：轻度降权
如果来源明确说明 actively exploited / in the wild / breach / incident / zero-day：可抵消一部分历史降权，避免错过真正重大更新
```

选题门槛：

```text
发布适配分高、风险提醒少的素材优先作为主线
AI coding / workflow / MCP / RAG / eval 题优先看是否改变真实开发流程或工程决策
核心事实包含“声称 / 据称 / if true / claimed / alleged / 未经证实 / 未确认”时，不能进入 FULL_ARTICLE，最多作为 SHORT_OBSERVATION 或正文引子
RSS 分高但属于维护性通知的素材，通常只能作为配置提醒或安全公告，不宜写成今日头条
安全类内容只有来源明确说明 actively exploited / in the wild / breach / incident 时，才能写成真实攻击事件
历史降权高的素材或领域，除非有明确重大更新，否则不要继续作为今日主线
成文候选会限制单一领域数量，避免 AI Agent / 安全类素材连续几天挤满 Top N
```

### 文章生成策略

文章重点回答：

```text
今天最值得看的具体问题是什么
发生了什么
它改变了哪段工作流、工程约束、生态关系或风险边界
谁会受到影响
读者可以怎么小范围验证或调整
风险和不确定性是什么
来源证据在哪里
```

如果素材里有未经确认的安全/入侵类声称，文章标题和主线必须转向可验证问题，例如：

```text
AI Agent 上线前为什么需要预部署验证
企业 Agent 的权限边界应该如何验证
Agent workflow 进入生产前要补哪几类测试
```

不要把标题写成：

```text
某模型被攻破
某公司遭入侵
某技术预览爆出安全事件
```

除非来源提供官方确认、独立调查或可核验证据。

AI coding / vibe coding / workflow 类文章必须写清：

```text
原来怎么做
现在多了什么能力
它改变的是开发流程的哪一段
适合谁，不适合谁
如何用一个小实验验证价值
需要注意的权限、质量、成本、稳定性或团队协作问题
```

AI 工程化类文章必须优先解释：

```text
工具链如何接入
评测或 benchmark 能说明什么，不能说明什么
RAG / MCP / tool use / browser use 等能力的工程边界
部署、成本、观测、安全和回滚问题
```

标题和开头要提高阅读兴趣，可以使用：

```text
具体问题
反常识判断
趋势冲突
机会窗口
风险提醒
工作流变化
```

但不要标题党，不要夸张承诺。

### 发布前审稿

成稿后还会生成发布前审稿：

```text
检查标题是否夸张
检查开头是否在 150 字内给出具体问题或冲突
检查是否把公告写成事故
检查是否把未经证实的安全/入侵类声称放进标题或主线
检查是否把单来源观察写成行业定论
检查相对日期
检查推测 URL 或无来源判断
硬性核对标题、开头、今日主线、意义和行动建议中的日期、年份、百分比、百分点、模型名、数据集名、benchmark/评测数字、工具数量、场景数量等具体数字
凡是来源证据摘录中找不到明确支持，或与来源不一致的数字，必须标为 high，并触发修改
检查行动建议是否具体，避免“持续关注”“加强学习”这类无信息量表达
检查是否适合插件同步到多平台
如果审稿不通过，系统会自动改写一次
```

## 信息源

信息源配置：

```text
config\sources.json
```

当前主要源包括：

```text
OpenAI
Anthropic（当前 RSS 可能返回 404，保留观察）
Google AI / Google Research / Google DeepMind
Microsoft Research
arXiv
Hacker News
GitHub Blog / GitHub Changelog
Hugging Face Blog
LangChain Blog / LangChain Changelog
Sourcegraph Blog
JetBrains AI Blog
n8n Blog
Vercel Blog
Replicate Blog
Instant Blog
Simon Willison
Latent Space
Stack Overflow Blog
Docker Blog
Kubernetes Blog
CNCF Blog
Cloudflare Blog
APNIC Blog
Krebs on Security
Schneier on Security
The Hacker News
Google Security Blog
Google Project Zero
CISA Cybersecurity Advisories
SANS Internet Storm Center
Trail of Bits Blog
Unit 42
Cisco Talos Blog
AWS News Blog / AWS Machine Learning Blog / AWS Architecture Blog
Azure Blog
Netflix Tech Blog
```

后续可增加：

```text
GitHub Trending
Papers with Code
LlamaIndex / AutoGen / CrewAI / Continue / Aider / Cursor / Windsurf
更多 AI coding、AI IDE、Agent workflow、eval、RAG、MCP 方向源
更多安全厂商研究博客
网络工程厂商技术博客
注意：新增源必须先验证 RSS/Atom 可拉取，再写入 config\sources.json，避免坏源拖慢每日抓取。
```

## 封面

每次生成文章时，会生成封面提示词：

```text
out\YYYY-MM-DD\cover-prompt-时间.txt
```

当前流程：

```text
复制封面提示词
-> 使用图片模型生成封面
-> 上传到目标平台
```

后续可接入图片模型 API，自动生成横版封面和小红书竖版封面。

## 常见问题

### Codex 出现 memory allocation failed

这是 Codex 桌面程序自身内存错误，不是内容系统错误。

处理：

```text
点击重新加载
或关闭 Codex 后重新打开
```

通常不需要重启 n8n、Docker、worker。

系统健康检查：

```powershell
cd E:\社区账号\content-pipeline
docker compose ps
Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8020/health"
Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8010/content-pool-latest.html"
Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8010/draft-latest.html"
```

### n8n 执行成功但页面没更新

检查：

```text
out
site\content-pool-latest.html
site\draft-latest.html
```

如果文件时间没有变化，检查 worker：

```powershell
Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8020/health"
```

### Wechatsync 无法识别文章

确认：

```text
访问的是 http://localhost:8010/draft-latest.html
浏览器已登录目标平台
Wechatsync 插件已启用
页面正文能正常显示
```

## 可清理内容

优先保留：

```text
out\content-pool-latest.md
out\content-pool-latest.json
out\draft-latest.md
out\YYYY-MM-DD\最新 content-pool-时间.md
out\YYYY-MM-DD\最新 content-pool-时间.json
out\YYYY-MM-DD\最新 daily-digest-时间.md
out\YYYY-MM-DD\最新 cover-prompt-时间.txt
site\content-pool-latest.html
site\draft-latest.html
```

可删除的通常是：

```text
out\draft-*.md              早期单链接测试草稿
out\旧日期\daily-digest-*.md    旧日报归档
out\旧日期\cover-prompt-*.txt   旧封面提示词
out\旧日期\content-pool-*.md    旧内容池归档
out\旧日期\content-pool-*.json  旧内容池归档
```

注意：按当前安全规则，不要批量删除文件或目录。如需清理，只能一次删除一个明确路径的单个文件，或由用户手动处理。

`E:\社区账号\tools\Wechatsync-2` 是之前尝试构建 Wechatsync 源码时复制的目录。当前系统使用官方成品插件，不依赖该目录。

## 后续改进方向

优先级较高：

1. 增加信息源质量评分，自动淘汰低质量源。
2. 继续优化历史去重，沉淀更稳定的选题库和主题冷却策略。
3. 增加主题细分看板：AI coding、Agent workflow、AI 工程化、安全、基础设施、开源工具分别统计信号强度。
4. 增加“高质量选题理由”字段，让候选页明确展示问题意识、行动价值、证据强度和风险边界。
5. 自动生成公众号、知乎、小红书、头条等平台版本。
6. 自动生成封面图。
7. 增加信息源稳定性监控，对长期 404、超时或证书失败的信息源降权或暂停。
8. 接入飞书多维表格或其他选题库，把今日内容池沉淀为可复盘的选题资产。

中长期方向：

```text
多账号内容矩阵
选题库
爆款标题库
数据反馈闭环
阅读量/收藏/评论反向优化提示词
```

## 质量原则

这套系统定位是“半自动内容编辑部”，不是全自动洗稿机器。

必须保留：

```text
来源链接
人工审核
事实核查
选题闸门
写作模式降级
证据边界说明
平台草稿确认
封面和标题人工判断
```

不建议做：

```text
全自动发布
无来源改写
批量洗稿
夸张标题
不可验证的趋势判断
把单来源写成行业定论
把普通产品更新包装成重大趋势
用空泛建议凑结尾
```

长期质量比短期数量更重要。

判断一篇文章是否值得发布，优先看：

```text
标题是否具体
开头是否有问题意识
主线是否单一且成立
事实是否都能回到来源
判断是否有边界
行动建议是否可执行
读者看完是否知道下一步做什么
```

## 本次项目总结补充

当前项目已经形成可实际使用的 MVP：日报和指定主题两条内容链路均可生成文章、保留来源、进入人工审核并生成平台版本；n8n 已作为每日调度器，浏览器插件仍作为人工确认后的发布辅助工具。

后续不建议为了追求全自动而扩大风险。优先稳定运行、备份运行数据、记录真实失败，再根据实际问题创建新的功能分支和任务卡。
