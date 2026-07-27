import html
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"
SITE_DIR = ROOT / "site"


PLATFORMS = [
    {
        "key": "douyin",
        "label": "抖音",
        "cover": "3:4",
        "fields": [
            ("title", "文章标题", 30),
            ("summary", "文章摘要", 30),
            ("hashtags", "话题", None),
            ("cover_ratio", "封面比例", None),
        ],
        "steps": ["标题和摘要均不超过 30 字", "添加话题", "上传 3:4 封面"],
    },
    {
        "key": "zhihu",
        "label": "知乎",
        "cover": "16:9",
        "fields": [
            ("title", "标题", 50),
            ("topics", "文章话题", None),
            ("summary", "摘要", 120),
            ("ai_statement", "创作声明", None),
            ("cover_ratio", "封面比例", None),
        ],
        "steps": ["添加文章话题", "创作声明选择“包含 AI 辅助创作”", "上传 16:9 封面"],
    },
    {
        "key": "juejin",
        "label": "稀土掘金",
        "cover": "16:9",
        "fields": [
            ("category", "分类", None),
            ("tags", "标签", None),
            ("summary", "编辑摘要", 100),
            ("cover_ratio", "封面比例", None),
        ],
        "steps": ["分类固定选择“人工智能”", "标签搜索不到时选择“人工智能”", "编辑摘要不超过 100 字", "上传 16:9 封面"],
    },
    {
        "key": "bilibili",
        "label": "B站",
        "cover": "16:9",
        "fields": [
            ("title", "标题", 80),
            ("topic", "话题", 20),
            ("ai_statement", "创作声明", None),
            ("cover_ratio", "封面比例", None),
        ],
        "steps": ["点击“自定义封面”后上传 16:9 封面", "创作声明点击“AI 辅助创作声明”", "只添加 1 个话题；搜索不到时选相关话题中热度最高的一个"],
    },
    {
        "key": "csdn",
        "label": "CSDN",
        "cover": "16:9",
        "fields": [
            ("title", "标题", 100),
            ("tags", "文章标签", None),
            ("summary", "文章摘要", 256),
            ("ai_statement", "创作声明", None),
            ("cover_ratio", "封面比例", None),
        ],
        "steps": ["添加文章标签", "摘要最多 256 字", "创作声明选择“部分由 AI 辅助生成”", "上传 16:9 封面"],
    },
    {
        "key": "xiaohongshu",
        "label": "小红书",
        "cover": "3:4",
        "fields": [
            ("title", "标题", 20),
            ("hashtags", "话题", None),
            ("ai_statement", "内容类型声明", None),
            ("cover_ratio", "封面比例", None),
        ],
        "steps": ["打开右上角草稿箱中最新一篇", "点击一键排版并等待完成", "点击下一步后在图片编辑中添加 3:4 封面", "内容类型声明选择“笔记包含 AI 合成内容”", "添加话题", "标题不超过 20 字"],
    },
]


DEFAULTS = {
    "douyin": {"cover_ratio": "3:4", "cover_size": "3:4"},
    "zhihu": {"cover_ratio": "16:9", "ai_statement": "包含 AI 辅助创作"},
    "juejin": {"category": "人工智能", "cover_ratio": "16:9"},
    "bilibili": {"topic": "人工智能", "cover_ratio": "16:9", "cover_size": "16:9", "ai_statement": "AI 辅助创作声明"},
    "csdn": {"cover_ratio": "16:9", "ai_statement": "部分由 AI 辅助生成"},
    "xiaohongshu": {"cover_ratio": "3:4", "cover_size": "3:4", "ai_statement": "笔记包含 AI 合成内容"},
}


def clean_text(value, preserve_lines=False):
    if isinstance(value, list):
        return "\n".join(clean_text(item) for item in value if clean_text(item))
    value = str(value or "")
    value = value.replace("\u00a0", " ").replace("\u3000", " ")
    if preserve_lines:
        lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in value.splitlines()]
        lines = [line for line in lines if line]
        return "\n".join(lines)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def limit_text(value, max_len):
    value = clean_text(value)
    if max_len is None or len(value) <= max_len:
        return value
    return value[: max_len - 1].rstrip("，。；、 ") + "…"


def normalize_pack(data):
    pack = {}
    fallback_title = clean_text(
        data.get("zhihu", {}).get("title")
        or data.get("csdn", {}).get("title")
        or data.get("douyin", {}).get("title")
    )
    fallback_summary = clean_text(
        data.get("zhihu", {}).get("summary")
        or data.get("csdn", {}).get("summary")
        or data.get("douyin", {}).get("summary")
    )
    fallback_tags = (
        data.get("zhihu", {}).get("topics")
        or data.get("douyin", {}).get("hashtags")
        or ["人工智能"]
    )
    for platform in PLATFORMS:
        key = platform["key"]
        fields = dict(DEFAULTS.get(key, {}))
        fields.update(data.get(key, {}) or {})
        if key == "juejin":
            fields["category"] = "人工智能"
        fields["cover_ratio"] = platform["cover"]
        fields["cover_size"] = platform["cover"]
        if key == "bilibili":
            fields.setdefault("title", fallback_title)
            fields.setdefault("summary", fallback_summary)
            fields.setdefault("topic", clean_text(fallback_tags[0] if isinstance(fallback_tags, list) else fallback_tags))
        for field, _, max_len in platform["fields"]:
            if field not in fields:
                continue
            if isinstance(fields[field], list):
                fields[field] = [limit_text(item, max_len) for item in fields[field] if clean_text(item)]
            else:
                fields[field] = limit_text(fields[field], max_len)
        pack[key] = fields
    return pack


def render_field(platform_key, field, label, value, max_len):
    preserve_lines = field in {"post", "body"}
    clean_value = clean_text(value, preserve_lines=preserve_lines)
    if isinstance(value, list):
        clean_items = [clean_text(item) for item in value if clean_text(item)]
    else:
        clean_items = [line for line in clean_value.splitlines() if line]
    length = len(clean_value)
    over = max_len is not None and length > max_len
    count = f"{length}/{max_len}" if max_len else str(length)
    status = " over" if over else ""
    attr_value = html.escape(clean_value, quote=True).replace("\n", "&#10;")
    attr_items = html.escape(json.dumps(clean_items, ensure_ascii=False, separators=(",", ":")), quote=True)
    return f"""
      <div class="field{status}" data-platform="{html.escape(platform_key)}" data-field="{html.escape(field)}" data-value="{attr_value}" data-items="{attr_items}" data-length="{length}" data-max="{html.escape(str(max_len or ''))}">
        <div class="field-head">
          <span class="field-label">{html.escape(label)}</span>
          <span class="count">{html.escape(count)}</span>
          <button type="button" class="copy" data-copy="{attr_value}">复制</button>
        </div>
        <pre>{html.escape(clean_value)}</pre>
      </div>
    """


def main() -> int:
    source = OUT_DIR / "platform-pack-latest.json"
    if not source.exists():
        raise FileNotFoundError(f"Missing platform pack: {source}")

    raw_data = json.loads(source.read_text(encoding="utf-8"))
    review_source = OUT_DIR / "platform-review-latest.json"
    platform_review = json.loads(review_source.read_text(encoding="utf-8")) if review_source.exists() else {}
    dryrun_source = OUT_DIR / "dryrun-latest.json"
    dryrun = json.loads(dryrun_source.read_text(encoding="utf-8-sig")) if dryrun_source.exists() else {}
    review_run_id = str(platform_review.get("run_id", ""))
    data = normalize_pack(raw_data)
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    sections = []
    for platform in PLATFORMS:
        key = platform["key"]
        fields = data.get(key, {})
        field_html = []
        for field, label, max_len in platform["fields"]:
            field_html.append(render_field(key, field, label, fields.get(field, ""), max_len))
        steps = "".join(f"<li>{html.escape(step)}</li>" for step in platform["steps"])
        review_item = platform_review.get("platforms", {}).get(key, {})
        review_status = str(review_item.get("status", "not_generated"))
        dryrun_item = dryrun.get("platforms", {}).get(key, {})
        dryrun_status = str(dryrun_item.get("status", "not_run"))
        dryrun_fields = ", ".join(str(item) for item in dryrun_item.get("available_fields", []))
        dryrun_entry = "是" if dryrun_item.get("entry_detected") else "否"
        dryrun_login = "是" if dryrun_item.get("login_detected") else "否"
        dryrun_challenge = "是" if dryrun_item.get("challenge_detected") else "否"
        dryrun_error = str(dryrun_item.get("error") or "")
        dryrun_html = f"""
              <div class="dryrun" id="dryrun-{html.escape(key)}" data-dryrun="{html.escape(key)}">
                <div><strong>DryRun 状态：</strong><span class="dryrun-status">{html.escape(dryrun_status)}</span></div>
                <div class="dryrun-meta">入口识别：{dryrun_entry}　登录提示：{dryrun_login}　验证码/风控：{dryrun_challenge}</div>
                <div class="dryrun-meta">识别字段：{html.escape(dryrun_fields or "暂无")}</div>
                <div class="dryrun-error">{html.escape(dryrun_error)}</div>
                <button type="button" data-dryrun-retry="{html.escape(key)}">重试此平台 DryRun</button>
              </div>
        """
        review_controls = ""
        if review_run_id:
            review_controls = f"""
              <div class="platform-review" data-platform-review="{html.escape(key)}">
                <span>平台审核状态：<strong class="platform-status">{html.escape(review_status)}</strong></span>
                <textarea class="platform-note" placeholder="平台审核意见（可选）"></textarea>
                <button type="button" data-platform-status="approved">平台通过</button>
                <button type="button" data-platform-status="revision_requested">要求修改</button>
                <button type="button" data-platform-status="rejected">平台驳回</button>
              </div>
            """
        sections.append(
            f"""
            <section class="platform" id="platform-{html.escape(key)}" data-platform="{html.escape(key)}">
              <div class="platform-head">
                <div>
                  <h2>{html.escape(platform["label"])}</h2>
                  <p>封面：{html.escape(platform["cover"])}</p>
                </div>
                <a href="#platform-{html.escape(key)}">#{html.escape(key)}</a>
              </div>
              <div class="workflow">
                <h3>发布动作</h3>
                <ol>{steps}</ol>
              </div>
              {review_controls}
              {dryrun_html}
              <div class="fields">{''.join(field_html)}</div>
            </section>
            """
        )

    automation_json = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>平台发布字段包</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: #f4f6f8;
      color: #17202a;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 30px 18px 72px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 30px;
      letter-spacing: 0;
    }}
    .hint {{
      margin: 0 0 22px;
      color: #667085;
      line-height: 1.7;
    }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 0 0 18px;
    }}
    .toolbar a {{
      color: #0b5cad;
      background: #fff;
      border: 1px solid #d7dee8;
      border-radius: 6px;
      padding: 7px 10px;
      text-decoration: none;
      font-size: 14px;
    }}
    .platform {{
      background: #fff;
      border: 1px solid #d8dee8;
      border-radius: 8px;
      margin: 16px 0;
      overflow: hidden;
    }}
    .platform-head {{
      display: flex;
      justify-content: space-between;
      gap: 14px;
      align-items: center;
      padding: 16px 18px;
      background: #eef4fb;
      border-bottom: 1px solid #d8dee8;
    }}
    h2 {{
      margin: 0;
      font-size: 21px;
    }}
    .platform-head p {{
      margin: 5px 0 0;
      color: #57606a;
    }}
    .platform-head a {{
      color: #57606a;
      text-decoration: none;
      font-size: 13px;
    }}
    .workflow {{
      padding: 14px 18px;
      border-bottom: 1px solid #edf1f5;
    }}
    h3 {{
      margin: 0 0 8px;
      font-size: 15px;
      color: #3a4655;
    }}
    ol {{
      margin: 0;
      padding-left: 22px;
      color: #3a4655;
      line-height: 1.75;
    }}
    .fields {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 12px;
      padding: 16px 18px 18px;
    }}
    .dryrun {{
      margin: 14px 18px 0;
      padding: 12px 14px;
      border: 1px solid #d8dee8;
      border-radius: 8px;
      background: #f8fafc;
      line-height: 1.7;
    }}
    .dryrun-meta {{ color: #57606a; font-size: 13px; }}
    .dryrun-error {{ color: #b42318; white-space: pre-wrap; word-break: break-word; }}
    .dryrun button {{
      margin-top: 7px;
      border: 1px solid #b8c4d2;
      background: #fff;
      color: #0b5cad;
      border-radius: 6px;
      padding: 5px 9px;
      cursor: pointer;
    }}
    .field {{
      border: 1px solid #d8dee8;
      border-radius: 8px;
      background: #fbfcfe;
      overflow: hidden;
    }}
    .field.over {{
      border-color: #d92d20;
      background: #fff7f6;
    }}
    .field-head {{
      display: grid;
      grid-template-columns: 1fr auto auto;
      gap: 10px;
      align-items: center;
      padding: 10px 12px;
      border-bottom: 1px solid #e6ebf1;
    }}
    .field-label {{
      font-weight: 700;
      color: #273444;
    }}
    .count {{
      color: #667085;
      font-variant-numeric: tabular-nums;
      font-size: 13px;
    }}
    button.copy {{
      border: 1px solid #b8c4d2;
      background: #fff;
      color: #0b5cad;
      border-radius: 6px;
      padding: 5px 9px;
      cursor: pointer;
    }}
    pre {{
      margin: 0;
      min-height: 48px;
      padding: 12px;
      white-space: pre-wrap;
      word-break: break-word;
      font: inherit;
      line-height: 1.55;
    }}
    script[type="application/json"] {{ display: none; }}
  </style>
</head>
<body>
  <main>
    <h1>平台发布字段包</h1>
    <p class="hint">面向自动化发文使用。每个字段已去掉首尾空格并压缩多余空白；Playwright 可通过 <code>[data-platform][data-field]</code> 读取 <code>data-value</code>。</p>
    <nav class="toolbar">
      {''.join(f'<a href="#platform-{html.escape(item["key"])}">{html.escape(item["label"])}</a>' for item in PLATFORMS)}
    </nav>
    {''.join(sections)}
    <script id="platform-pack-data" type="application/json">{automation_json}</script>
  </main>
  <script>
    const platformReviewContext = {json.dumps({"run_id": review_run_id}, ensure_ascii=False)};
    document.querySelectorAll('button.copy').forEach((button) => {{
      button.addEventListener('click', async () => {{
        const value = button.dataset.copy || '';
        await navigator.clipboard.writeText(value);
        const old = button.textContent;
        button.textContent = '已复制';
        setTimeout(() => button.textContent = old, 900);
      }});
    }});
    document.querySelectorAll('[data-platform-review] button[data-platform-status]').forEach((button) => {{
      button.addEventListener('click', async () => {{
        const panel = button.closest('[data-platform-review]');
        const platform = panel.dataset.platformReview;
        const note = panel.querySelector('.platform-note').value;
        panel.querySelectorAll('button').forEach((item) => item.disabled = true);
        try {{
          const response = await fetch('http://localhost:8020/platform-review', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ ...platformReviewContext, platform, status: button.dataset.platformStatus, note }})
          }});
          const payload = await response.json();
          if (!response.ok || !payload.ok) throw new Error(payload.error || '保存失败');
          panel.querySelector('.platform-status').textContent = payload.platform_review.status;
        }} catch (error) {{
          window.alert('平台审核保存失败：' + error.message);
        }} finally {{
          panel.querySelectorAll('button').forEach((item) => item.disabled = false);
        }}
      }});
    }});
    document.querySelectorAll('[data-dryrun-retry]').forEach((button) => {{
      button.addEventListener('click', async () => {{
        const platform = button.dataset.dryrunRetry;
        const panel = button.closest('[data-dryrun]');
        button.disabled = true;
        button.textContent = '正在检查...';
        try {{
          const response = await fetch('http://localhost:8020/dryrun', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ platform }})
          }});
          const payload = await response.json();
          if (!response.ok || !payload.ok) throw new Error(payload.error || 'DryRun 失败');
          const item = payload.dryrun && payload.dryrun.platforms && payload.dryrun.platforms[platform];
          if (item) panel.querySelector('.dryrun-status').textContent = item.status || 'unknown';
          window.location.reload();
        }} catch (error) {{
          panel.querySelector('.dryrun-status').textContent = 'failed';
          panel.querySelector('.dryrun-error').textContent = error.message;
        }} finally {{
          button.disabled = false;
          button.textContent = '重试此平台 DryRun';
        }}
      }});
    }});
  </script>
</body>
</html>
"""
    out_path = SITE_DIR / "platform-pack-latest.html"
    out_path.write_text(page, encoding="utf-8")
    print("Rendered platform pack:")
    print(out_path)
    print("Open with:")
    print("http://localhost:8010/platform-pack-latest.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
