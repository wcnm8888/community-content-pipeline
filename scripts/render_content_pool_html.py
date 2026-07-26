import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"
SITE_DIR = ROOT / "site"


def render_notes(notes: list[str]) -> str:
    return "；".join(str(note) for note in notes)


def main() -> int:
    source = OUT_DIR / "content-pool-latest.json"
    if not source.exists():
        raise FileNotFoundError(f"Missing content pool: {source}")

    data = json.loads(source.read_text(encoding="utf-8"))
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    recommended = data.get("recommended_topic") or {}
    signal_rows = []
    for signal in data.get("category_signals", []):
        signal_rows.append(
            "<tr>"
            f"<td>{html.escape(signal['category'])}</td>"
            f"<td>{signal['signal_score']}</td>"
            f"<td>{signal['count']}</td>"
            f"<td>{signal['top_score']}</td>"
            f"<td>{signal['average_score']}</td>"
            "</tr>"
        )

    selected_rows = []
    for item in data.get("selected_for_reader", []):
        selected_rows.append(
            "<tr>"
            f"<td>{item['rank']}</td>"
            f"<td><a href=\"{html.escape(item['url'])}\" target=\"_blank\" rel=\"noopener noreferrer\">{html.escape(item['title'])}</a></td>"
            f"<td>{html.escape(item['source'])}</td>"
            f"<td>{html.escape(item['category'])}</td>"
            f"<td>{item['score']}</td>"
            f"<td>{item.get('editorial_score', '')}</td>"
            f"<td>{html.escape(str(item.get('content_type', '')))}</td>"
            f"<td>{html.escape(render_notes(item['selection_notes']))}</td>"
            "</tr>"
        )

    pool_rows = []
    for item in data.get("content_pool", []):
        pool_rows.append(
            "<tr>"
            f"<td>{item['rank']}</td>"
            f"<td><a href=\"{html.escape(item['url'])}\" target=\"_blank\" rel=\"noopener noreferrer\">{html.escape(item['title'])}</a></td>"
            f"<td>{html.escape(item['source'])}</td>"
            f"<td>{html.escape(item['category'])}</td>"
            f"<td>{item['score']}</td>"
            f"<td>{item.get('editorial_score', '')}</td>"
            f"<td>{html.escape(str(item.get('content_type', '')))}</td>"
            f"<td>{html.escape(item['published'])}</td>"
            "</tr>"
        )

    rule = data["scoring_rule"]
    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>今日内容池</title>
  <style>
    body {{
      margin: 0;
      background: #f6f7f9;
      color: #1f2328;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
      line-height: 1.6;
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 34px 18px 72px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 30px;
    }}
    h2 {{
      margin: 28px 0 12px;
      font-size: 21px;
    }}
    .hint, .meta {{
      color: #667085;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 12px;
      margin: 20px 0 8px;
    }}
    .metric {{
      background: #fff;
      border: 1px solid #d8dee4;
      border-radius: 8px;
      padding: 14px 16px;
    }}
    .metric strong {{
      display: block;
      font-size: 24px;
      margin-top: 4px;
    }}
    .panel {{
      background: #fff;
      border: 1px solid #d8dee4;
      border-radius: 8px;
      padding: 16px 18px;
      margin: 16px 0;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: #fff;
      border: 1px solid #d8dee4;
      border-radius: 8px;
      overflow: hidden;
    }}
    th, td {{
      border-bottom: 1px solid #edf1f5;
      padding: 10px 12px;
      text-align: left;
      vertical-align: top;
      font-size: 14px;
    }}
    th {{
      background: #f6f8fa;
      color: #57606a;
      font-weight: 600;
    }}
    a {{
      color: #0969da;
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
    code {{
      background: #f6f8fa;
      padding: 2px 5px;
      border-radius: 4px;
      font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
      font-size: 0.92em;
    }}
  </style>
</head>
<body>
  <main>
    <h1>今日内容池</h1>
    <p class="hint">展示 RSS 初筛后的候选内容、领域信号和入选成文候选。它解释“为什么今天可能适合写这个主题”，不替代人工审核。</p>

    <div class="summary">
      <div class="metric">RSS 候选<strong>{data['collected_count']}</strong></div>
      <div class="metric">内容池<strong>{data['pool_size']}</strong></div>
      <div class="metric">成文候选<strong>{data['selected_for_reader_count']}</strong></div>
      <div class="metric">建议主线<strong>{html.escape(str(recommended.get('category', '无')))}</strong></div>
    </div>

    <section class="panel">
      <h2>选择规则</h2>
      <p>单篇分数：<code>{html.escape(rule['item_score'])}</code></p>
      <p>发布适配分：<code>{html.escape(rule.get('editorial_score', ''))}</code></p>
      <p>最终排序分：<code>{html.escape(rule.get('final_rank_score', ''))}</code></p>
      <p>领域信号：<code>{html.escape(rule['category_signal_score'])}</code></p>
      <p>{html.escape(rule['editorial_policy'])}</p>
      <p class="meta">生成时间：{html.escape(data['generated_at'])}</p>
    </section>

    <h2>领域信号排行</h2>
    <table>
      <thead><tr><th>领域</th><th>信号分</th><th>条数</th><th>最高单篇</th><th>均分</th></tr></thead>
      <tbody>{''.join(signal_rows)}</tbody>
    </table>

    <h2>入选成文候选</h2>
    <table>
      <thead><tr><th>#</th><th>标题</th><th>来源</th><th>领域</th><th>RSS</th><th>适配</th><th>类型</th><th>入选理由</th></tr></thead>
      <tbody>{''.join(selected_rows)}</tbody>
    </table>

    <h2>完整内容池</h2>
    <table>
      <thead><tr><th>#</th><th>标题</th><th>来源</th><th>领域</th><th>RSS</th><th>适配</th><th>类型</th><th>发布时间</th></tr></thead>
      <tbody>{''.join(pool_rows)}</tbody>
    </table>
  </main>
</body>
</html>
"""
    out_path = SITE_DIR / "content-pool-latest.html"
    out_path.write_text(page, encoding="utf-8")
    print("Rendered content pool:")
    print(out_path)
    print("Open with:")
    print("http://localhost:8010/content-pool-latest.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
