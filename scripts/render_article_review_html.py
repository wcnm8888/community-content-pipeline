import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"
SITE_DIR = ROOT / "site"


def render_bool(value: object) -> str:
    return "是" if value else "否"


def render_findings(findings: list[dict]) -> str:
    if not findings:
        return "<p class=\"ok\">未发现明显问题。</p>"
    rows = []
    for item in findings:
        severity = str(item.get("severity", "medium"))
        rows.append(
            "<tr>"
            f"<td><span class=\"badge {html.escape(severity)}\">{html.escape(severity)}</span></td>"
            f"<td>{html.escape(str(item.get('issue', '')))}</td>"
            f"<td>{html.escape(str(item.get('suggestion', '')))}</td>"
            "</tr>"
        )
    return (
        "<table>"
        "<thead><tr><th>级别</th><th>问题</th><th>建议</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def main() -> int:
    source = OUT_DIR / "article-review-latest.json"
    if not source.exists():
        raise FileNotFoundError(f"Missing article review: {source}")

    review = json.loads(source.read_text(encoding="utf-8"))
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    score = int(review.get("quality_score", 0) or 0)
    status_class = "good" if review.get("safe_to_sync") else "warn"

    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>发布前审稿</title>
  <style>
    body {{
      margin: 0;
      background: #f6f7f9;
      color: #1f2328;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
      line-height: 1.65;
    }}
    main {{
      max-width: 980px;
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
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 12px;
      margin: 20px 0;
    }}
    .metric {{
      background: #fff;
      border: 1px solid #d8dee4;
      border-radius: 8px;
      padding: 14px 16px;
    }}
    .metric strong {{
      display: block;
      font-size: 26px;
      margin-top: 4px;
    }}
    .good strong {{
      color: #1a7f37;
    }}
    .warn strong {{
      color: #bf8700;
    }}
    .panel {{
      background: #fff;
      border: 1px solid #d8dee4;
      border-radius: 8px;
      padding: 16px 18px;
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
    }}
    .badge {{
      display: inline-block;
      min-width: 54px;
      border-radius: 999px;
      padding: 2px 8px;
      text-align: center;
      font-size: 12px;
      color: #fff;
      background: #57606a;
    }}
    .high {{
      background: #cf222e;
    }}
    .medium {{
      background: #bf8700;
    }}
    .low {{
      background: #57606a;
    }}
    .ok {{
      color: #1a7f37;
    }}
  </style>
</head>
<body>
  <main>
    <h1>发布前审稿</h1>
    <p>用于同步前检查标题、事实边界、相对日期、来源和平台风险。</p>
    <div class="summary">
      <div class="metric {status_class}">质量分<strong>{score}</strong></div>
      <div class="metric">需要修改<strong>{render_bool(review.get('needs_revision'))}</strong></div>
      <div class="metric {status_class}">建议同步<strong>{render_bool(review.get('safe_to_sync'))}</strong></div>
      <div class="metric">已自动改写<strong>{render_bool(review.get('revision_applied'))}</strong></div>
    </div>
    <section class="panel">
      <h2>总评</h2>
      <p>{html.escape(str(review.get('summary', '')))}</p>
    </section>
    <h2>问题清单</h2>
    {render_findings(review.get('findings', []))}
    <h2>自动改写后仍需人工注意</h2>
    {render_findings(review.get('post_revision_findings', []))}
  </main>
</body>
</html>
"""
    out_path = SITE_DIR / "article-review-latest.html"
    out_path.write_text(page, encoding="utf-8")
    print("Rendered article review:")
    print(out_path)
    print("Open with:")
    print("http://localhost:8010/article-review-latest.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
