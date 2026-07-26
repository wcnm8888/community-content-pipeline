import argparse
import html
from pathlib import Path

from render_draft_html import find_title, markdown_to_html


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"
SITE_DIR = ROOT / "site"


def latest_markdown() -> Path:
    latest = OUT_DIR / "knowledge-share-latest.md"
    if latest.exists():
        return latest
    files = sorted(OUT_DIR.glob("*/knowledge-share-*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"No knowledge-share-*.md files found in {OUT_DIR}")
    return files[0]


def render(markdown_path: Path) -> Path:
    markdown = markdown_path.read_text(encoding="utf-8")
    title = find_title(markdown, markdown_path.stem)
    article_html = markdown_to_html(markdown)
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SITE_DIR / "knowledge-share-latest.html"
    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} - 知识分享文章预览</title>
  <style>
    body {{
      margin: 0;
      background: #f6f7f9;
      color: #1f2328;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
      line-height: 1.78;
    }}
    main {{
      max-width: 780px;
      margin: 0 auto;
      padding: 38px 22px 72px;
      background: #fff;
      min-height: 100vh;
    }}
    .page-note {{
      margin: 0 0 28px;
      color: #667085;
      font-size: 14px;
      border-bottom: 1px solid #edf1f5;
      padding-bottom: 14px;
    }}
    article {{
      font-size: 17px;
    }}
    h1 {{
      font-size: 30px;
      line-height: 1.28;
      margin: 0 0 28px;
    }}
    h2 {{
      font-size: 22px;
      margin: 34px 0 12px;
    }}
    h3 {{
      font-size: 19px;
      margin: 26px 0 10px;
    }}
    p, ul, blockquote {{
      margin: 14px 0;
    }}
    ul {{
      padding-left: 24px;
    }}
    li {{
      margin: 8px 0;
    }}
    blockquote {{
      border-left: 4px solid #d0d7de;
      padding: 8px 16px;
      background: #f6f8fa;
      color: #57606a;
    }}
    code {{
      background: #f6f8fa;
      padding: 2px 5px;
      border-radius: 4px;
      font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
      font-size: 0.92em;
    }}
    a {{
      color: #0969da;
    }}
  </style>
</head>
<body>
  <main>
    <p class="page-note">知识分享文章预览。用于发布前检查结构、事实边界、来源链接和平台适配。</p>
    <article id="article">
{article_html}
    </article>
  </main>
</body>
</html>
"""
    out_path.write_text(page, encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path)
    args = parser.parse_args()
    source = args.file if args.file else latest_markdown()
    out_path = render(source)
    print("Rendered knowledge share HTML:")
    print(out_path)
    print("Open with:")
    print("http://localhost:8010/knowledge-share-latest.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
