import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"
SITE_DIR = ROOT / "site"


def render_list(values: object) -> str:
    if not isinstance(values, list) or not values:
        return "<li>无</li>"
    return "".join(f"<li>{html.escape(str(value))}</li>" for value in values)


def main() -> int:
    source = OUT_DIR / "topic-candidates-latest.json"
    if not source.exists():
        raise FileNotFoundError(f"Missing topic candidates: {source}")

    data = json.loads(source.read_text(encoding="utf-8"))
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    gate = data.get("gate", {})
    gate_class = "good" if gate.get("decision") in ("WRITE", "WRITE_SHORT") else "warn"

    sections = []
    for index, candidate in enumerate(data.get("candidates", []), 1):
        grade = str(candidate.get("grade", "REJECT"))
        sections.append(
            f"""
            <section>
              <h2>{index}. <span class="badge {html.escape(grade.lower())}">{html.escape(grade)}</span> {html.escape(str(candidate.get('topic', '')))}</h2>
              <p><strong>候选标题：</strong>{html.escape(str(candidate.get('working_title', '')))}</p>
              <p><strong>建议动作：</strong>{html.escape(str(candidate.get('recommended_action', '')))}</p>
              <p><strong>为什么值得写：</strong>{html.escape(str(candidate.get('why_worth_writing', '')))}</p>
              <p><strong>为什么可能不值得写：</strong>{html.escape(str(candidate.get('why_not', '')))}</p>
              <div class="grid">
                <div><h3>支撑来源</h3><ul>{render_list(candidate.get('supporting_sources', []))}</ul></div>
                <div><h3>核心事实</h3><ul>{render_list(candidate.get('core_facts', []))}</ul></div>
                <div><h3>发布风险</h3><ul>{render_list(candidate.get('publishing_risks', []))}</ul></div>
              </div>
            </section>
            """
        )

    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>选题候选</title>
  <style>
    body {{
      margin: 0;
      background: #f6f7f9;
      color: #1f2328;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
      line-height: 1.65;
    }}
    main {{
      max-width: 1080px;
      margin: 0 auto;
      padding: 34px 18px 72px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 30px;
    }}
    h2 {{
      margin: 0 0 12px;
      font-size: 21px;
    }}
    h3 {{
      margin: 12px 0 6px;
      font-size: 15px;
      color: #57606a;
    }}
    .summary, section {{
      background: #fff;
      border: 1px solid #d8dee4;
      border-radius: 8px;
      padding: 16px 18px;
      margin: 16px 0;
    }}
    .summary.good {{
      border-color: #2da44e;
    }}
    .summary.warn {{
      border-color: #bf8700;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
    }}
    ul {{
      margin: 6px 0 0;
      padding-left: 22px;
    }}
    li {{
      margin: 4px 0;
    }}
    .badge {{
      display: inline-block;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 12px;
      color: #fff;
      background: #57606a;
    }}
    .a {{
      background: #1a7f37;
    }}
    .b {{
      background: #2f6feb;
    }}
    .c {{
      background: #bf8700;
    }}
    .reject {{
      background: #cf222e;
    }}
  </style>
</head>
<body>
  <main>
    <h1>选题候选</h1>
    <p>先判断今天是否值得写主文，再决定是否进入正文生成。</p>
    <div class="summary {gate_class}">
      <p><strong>总体决策：</strong>{html.escape(str(data.get('overall_decision', '')))}</p>
      <p><strong>闸门：</strong>{html.escape(str(gate.get('decision', '')))}</p>
      <p><strong>写作模式：</strong>{html.escape(str(gate.get('mode', '')))}</p>
      <p><strong>原因：</strong>{html.escape(str(gate.get('reason', '')))}</p>
      <p><strong>总评：</strong>{html.escape(str(data.get('summary', '')))}</p>
    </div>
    {''.join(sections)}
  </main>
</body>
</html>
"""
    out_path = SITE_DIR / "topic-candidates-latest.html"
    out_path.write_text(page, encoding="utf-8")
    print("Rendered topic candidates:")
    print(out_path)
    print("Open with:")
    print("http://localhost:8010/topic-candidates-latest.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
