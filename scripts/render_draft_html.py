import argparse
import html
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"
SITE_DIR = ROOT / "site"


def latest_markdown() -> Path:
    latest = OUT_DIR / "draft-latest.md"
    if latest.exists():
        return latest
    files = sorted(OUT_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"No draft-*.md files found in {OUT_DIR}")
    return files[0]


def inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>',
        escaped,
    )
    return escaped


def markdown_to_html(markdown: str) -> str:
    lines = markdown.splitlines()
    parts = []
    paragraph = []
    in_comment = False
    in_list = False

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            text = " ".join(line.strip() for line in paragraph)
            parts.append(f"<p>{inline_markdown(text)}</p>")
            paragraph = []

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            parts.append("</ul>")
            in_list = False

    for raw in lines:
        line = raw.strip()
        if line.startswith("<!--"):
            in_comment = True
            continue
        if in_comment:
            if line.endswith("-->"):
                in_comment = False
            continue
        if not line:
            flush_paragraph()
            close_list()
            continue
        if line == "---":
            flush_paragraph()
            close_list()
            parts.append("<hr>")
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            parts.append(f"<h{level}>{inline_markdown(heading.group(2))}</h{level}>")
            continue
        bullet = re.match(r"^[-*]\s+(.+)$", line)
        numbered = re.match(r"^\d+\.\s+(.+)$", line)
        if bullet or numbered:
            flush_paragraph()
            if not in_list:
                parts.append("<ul>")
                in_list = True
            item = bullet.group(1) if bullet else numbered.group(1)
            parts.append(f"<li>{inline_markdown(item)}</li>")
            continue
        quote = re.match(r"^>\s?(.+)$", line)
        if quote:
            flush_paragraph()
            close_list()
            parts.append(f"<blockquote>{inline_markdown(quote.group(1))}</blockquote>")
            continue
        close_list()
        paragraph.append(line)

    flush_paragraph()
    close_list()
    return "\n".join(parts)


def find_title(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        match = re.match(r"^#\s+(.+)$", line.strip())
        if match:
            return re.sub(r"\*\*", "", match.group(1)).strip()
    return fallback


def render(markdown_path: Path) -> Path:
    markdown = markdown_path.read_text(encoding="utf-8")
    title = find_title(markdown, markdown_path.stem)
    article_html = markdown_to_html(markdown)
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SITE_DIR / "draft-latest.html"
    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
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
      padding: 48px 22px 72px;
      background: #fff;
      min-height: 100vh;
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
    print("Rendered HTML:")
    print(out_path)
    print("Open with:")
    print("http://localhost:8010/draft-latest.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
