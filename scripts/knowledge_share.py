import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from daily_digest import (
    FeedItem,
    clean_text,
    deepseek_chat,
    extract_evidence_sentences,
    extract_title_and_summary,
    fetch_text,
    load_env,
    log,
    parse_markdown_title,
    review_and_improve_article,
    sanitize_article,
    source_evidence_blocks,
    write_article_review,
    write_cover_prompt,
    write_platform_pack,
)
from run_manifest import RunManifest


CURRENT_MANIFEST: RunManifest | None = None


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "sources.json"
OUT_DIR = ROOT / "out"
PROMPT_PATH = ROOT / "prompts" / "knowledge-share.md"


@dataclass
class SourceCandidate:
    title: str
    url: str
    snippet: str = ""
    source_type: str = "technical_article"
    credibility_score: int = 50
    rank: int = 0
    content: str = ""
    risk_notes: list[str] = field(default_factory=list)


LOW_QUALITY_HINTS = [
    "coupon",
    "pricing",
    "alternatives to",
    "top 10",
    "best ",
    "sponsored",
    "press release",
    "转载",
    "广告",
    "营销",
    "推广",
    "聚合",
]


def normalized_url(url: str) -> str:
    return url.split("#", 1)[0].rstrip("/")


def parse_urls(values: list[str] | None) -> list[str]:
    urls: list[str] = []
    for value in values or []:
        for part in re.split(r"[\s,]+", value.strip()):
            if part.startswith(("http://", "https://")):
                urls.append(part)
    seen = set()
    result = []
    for url in urls:
        key = normalized_url(url).lower()
        if key not in seen:
            seen.add(key)
            result.append(normalized_url(url))
    return result


def classify_source(url: str, title: str = "") -> tuple[str, int, list[str]]:
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    path = parsed.path.lower()
    text = f"{domain} {path} {title}".lower()
    notes: list[str] = []
    source_type = "technical_article"
    score = 55

    if domain.endswith("github.com"):
        source_type = "github_project"
        score = 88
        if any(part in path for part in ("/issues/", "/pull/", "/releases", "/blob/")):
            score = 82
    elif "arxiv.org" in domain or "doi.org" in domain or "acm.org" in domain or "ieee.org" in domain:
        source_type = "paper"
        score = 84
    elif domain.endswith("modelcontextprotocol.io") or domain.startswith("docs.") or "/docs" in path or "documentation" in path:
        source_type = "official_docs"
        score = 92
    elif any(host in domain for host in ("openai.com", "anthropic.com", "googleblog.com", "microsoft.com", "github.blog", "cloudflare.com", "kubernetes.io", "docker.com")):
        source_type = "official_blog"
        score = 86
    elif any(host in domain for host in ("martinfowler.com", "simonwillison.net", "netflixtechblog.com", "engineering.", "blog.")):
        source_type = "engineering_blog"
        score = 74

    if any(hint in text for hint in LOW_QUALITY_HINTS):
        score -= 30
        notes.append("包含营销、榜单、转载或聚合页特征，需要谨慎使用。")
    if "medium.com" in domain or "dev.to" in domain:
        score -= 8
        notes.append("社区博客质量差异较大，不能单独支撑核心判断。")
    if score < 60 and not notes:
        notes.append("来源可信度一般，只适合作为辅助参考。")
    return source_type, max(0, min(100, score)), notes


def search_brave(env: dict, topic: str, angle: str, top_results: int) -> list[SourceCandidate]:
    api_key = env.get("SEARCH_API_KEY", "").strip()
    if not api_key or api_key in {"your-search-api-key", "sk-your-search-key"}:
        raise RuntimeError("SEARCH_API_KEY is not configured. Configure Brave Search or use --urls manual mode.")
    base_url = env.get("SEARCH_BASE_URL", "https://api.search.brave.com/res/v1/web/search").strip()
    query = f"{topic} {angle}".strip()
    params = f"?q={quote(query, safe='')}&count={max(1, min(top_results, 20))}&search_lang=en&country=US"
    req = Request(
        base_url.rstrip("/") + params,
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
            "User-Agent": "content-pipeline-mvp/1.0",
        },
    )
    with urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    candidates: list[SourceCandidate] = []
    for index, item in enumerate((payload.get("web") or {}).get("results", []), 1):
        url = str(item.get("url", "")).strip()
        if not url.startswith(("http://", "https://")):
            continue
        title = clean_text(str(item.get("title", "") or url))
        snippet = clean_text(str(item.get("description", "")))
        source_type, score, notes = classify_source(url, title)
        if score < 45:
            continue
        candidates.append(SourceCandidate(title=title, url=normalized_url(url), snippet=snippet, source_type=source_type, credibility_score=score, rank=index, risk_notes=notes))
    return dedupe_candidates(candidates)[:top_results]


def search_sources(env: dict, topic: str, angle: str, top_results: int) -> list[SourceCandidate]:
    provider = env.get("SEARCH_PROVIDER", "").strip().lower()
    if not provider:
        raise RuntimeError("SEARCH_PROVIDER is not configured. Configure SEARCH_PROVIDER=brave or use --urls manual mode.")
    if provider != "brave":
        raise RuntimeError(f"Unsupported SEARCH_PROVIDER={provider}. First version supports brave or --urls manual mode.")
    return search_brave(env, topic, angle, top_results)


def dedupe_candidates(candidates: list[SourceCandidate]) -> list[SourceCandidate]:
    seen = set()
    result: list[SourceCandidate] = []
    for candidate in sorted(candidates, key=lambda item: (-item.credibility_score, item.rank)):
        key = normalized_url(candidate.url).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def manual_candidates(urls: list[str]) -> list[SourceCandidate]:
    candidates = []
    for index, url in enumerate(urls, 1):
        source_type, score, notes = classify_source(url)
        candidates.append(SourceCandidate(title=url, url=url, source_type=source_type, credibility_score=score, rank=index, risk_notes=notes))
    return candidates


def read_sources(candidates: list[SourceCandidate], env: dict, reader_timeout: int) -> list[SourceCandidate]:
    reader_base = env.get("JINA_READER_BASE_URL", "https://r.jina.ai/").rstrip("/")
    readable: list[SourceCandidate] = []
    for index, candidate in enumerate(candidates, 1):
        try:
            log(f"Reading source {index}/{len(candidates)}: {candidate.url}")
            content = fetch_text(f"{reader_base}/{candidate.url}", timeout=reader_timeout).replace("\x00", "")
            if not content.strip():
                raise RuntimeError("empty reader response")
            candidate.content = content[:8000]
            title = parse_markdown_title(content)
            if title:
                candidate.title = title
            readable.append(candidate)
        except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError) as exc:
            candidate.risk_notes.append(f"Jina Reader 读取失败：{exc}")
            if candidate.snippet:
                candidate.content = candidate.snippet
                readable.append(candidate)
            else:
                log(f"WARN skipping unreadable source: {candidate.url} {exc}")
    return readable


def useful_examples_from_text(text: str, max_count: int = 3) -> list[str]:
    sentences = re.split(r"(?<=[。！？.!?])\s+", re.sub(r"\s+", " ", text or "").strip())
    patterns = ["example", "for example", "quickstart", "install", "npm ", "pip ", "docker ", "github", "示例", "例如", "上手", "安装", "用法", "代码"]
    result = []
    for sentence in sentences:
        if len(sentence) < 18:
            continue
        lower = sentence.lower()
        if any(pattern in lower for pattern in patterns):
            result.append(sentence[:280])
        if len(result) >= max_count:
            break
    return result


def source_to_feed_item(candidate: SourceCandidate) -> FeedItem:
    return FeedItem(
        title=candidate.title,
        link=candidate.url,
        summary=candidate.snippet,
        source=urlparse(candidate.url).netloc.lower(),
        category=candidate.source_type,
        weight=1,
        published=None,
        score=candidate.credibility_score,
        content_type=candidate.source_type,
        editorial_score=candidate.credibility_score,
        content=candidate.content[:5000],
    )


def build_material_cards(candidates: list[SourceCandidate], timestamp: str) -> tuple[dict, list[FeedItem]]:
    feed_items = [source_to_feed_item(candidate) for candidate in candidates]
    cards = []
    for index, (candidate, item) in enumerate(zip(candidates, feed_items), 1):
        facts = extract_evidence_sentences(item, max_count=5)
        cards.append({
            "rank": index,
            "title": candidate.title,
            "url": candidate.url,
            "source_type": candidate.source_type,
            "credibility_score": candidate.credibility_score,
            "key_facts": facts,
            "useful_examples": useful_examples_from_text(candidate.content),
            "cannot_infer": [
                "不能写资料中没有出现的日期、数字、性能结论或用户规模。",
                "不能把单一来源观点写成行业共识。",
                "不能把营销表述当作事实结论。",
            ],
            "risk_notes": candidate.risk_notes,
        })
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": timestamp,
        "cards": cards,
    }
    return payload, feed_items


def build_knowledge_prompt(topic: str, angle: str, audience: str, cards_payload: dict, source_items: list[FeedItem]) -> str:
    cards_text = json.dumps(cards_payload["cards"], ensure_ascii=False, indent=2)
    evidence = source_evidence_blocks(source_items, limit=8, excerpt_len=2200)
    angle_text = angle or "通俗清楚地解释给目标读者"
    return f"""请基于资料卡片和来源摘录，写一篇中文知识分享文章。

主题：{topic}
写作角度：{angle_text}
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
"""


def write_knowledge_outputs(article: str, metadata: dict, timestamp: str, run_dir: Path) -> tuple[Path, Path, Path, Path]:
    json_path = run_dir / f"knowledge-share-{timestamp}.json"
    md_path = run_dir / f"knowledge-share-{timestamp}.md"
    latest_json = OUT_DIR / "knowledge-share-latest.json"
    latest_md = OUT_DIR / "knowledge-share-latest.md"
    json_text = json.dumps(metadata, ensure_ascii=False, indent=2)
    front = (
        "<!--\n"
        "Generated by content-pipeline knowledge share\n"
        f"GeneratedAt: {metadata['generated_at']}\n"
        f"Topic: {metadata['topic']}\n"
        f"Angle: {metadata.get('angle', '')}\n"
        f"Sources: {len(metadata.get('materials', []))}\n"
        f"ArticleReview: article-review-{timestamp}.md\n"
        "-->\n\n"
    )
    md_text = front + article
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    return json_path, md_path, latest_json, latest_md


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True)
    parser.add_argument("--angle", default="")
    parser.add_argument("--audience", default="")
    parser.add_argument("--top-results", type=int, default=8)
    parser.add_argument("--reader-timeout", type=int, default=18)
    parser.add_argument("--retry-of", default=None, help="关联一次失败运行的 run_id，不改变正常输出流程")
    parser.add_argument("--urls", nargs="*")
    args = parser.parse_args()

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    env = load_env()
    audience = args.audience.strip() or config.get("profile", {}).get("audience", "")
    urls = parse_urls(args.urls)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_dir = OUT_DIR / time.strftime("%Y-%m-%d")
    run_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    global CURRENT_MANIFEST
    manifest = RunManifest(run_dir, "knowledge_share", timestamp, retry_of=args.retry_of)
    CURRENT_MANIFEST = manifest

    candidates = manifest.run_stage("source_candidates", lambda: manual_candidates(urls))
    if len(candidates) < args.top_results:
        try:
            candidates.extend(manifest.run_stage("source_search", lambda: search_sources(
                env, args.topic, args.angle, args.top_results
            )))
        except RuntimeError as exc:
            if not candidates:
                raise RuntimeError(f"{exc} You can run manual mode with --urls https://example.com") from exc
            manifest.skip_stage("source_search", str(exc))
            log(f"WARN search skipped: {exc}")
    candidates = dedupe_candidates(candidates)[: args.top_results]
    if not candidates:
        raise RuntimeError("No usable sources. Configure search API or pass at least one URL with --urls.")

    readable = manifest.run_stage("reader", lambda: read_sources(candidates, env, args.reader_timeout))
    if not readable:
        raise RuntimeError("No readable sources after Jina Reader extraction.")

    cards_payload, source_items = manifest.run_stage("material_cards", lambda: build_material_cards(readable, timestamp))
    prompt = build_knowledge_prompt(args.topic, args.angle, audience, cards_payload, source_items)
    log("Generating knowledge share article with DeepSeek...")
    article = manifest.run_stage(
        "article_generation",
        lambda: sanitize_article(deepseek_chat(env, prompt, system_prompt=PROMPT_PATH.read_text(encoding="utf-8"))),
    )
    article, review = manifest.run_stage(
        "article_review",
        lambda: review_and_improve_article(
            article,
            env,
            {"selected_for_reader": [
                {
                    "title": item.title,
                    "source": item.source,
                    "content_type": item.content_type,
                    "score": item.score,
                    "editorial_score": item.editorial_score,
                    "editorial_breakdown": {"caution_flags": []},
                }
                for item in source_items
            ]},
            source_items,
            content_kind="knowledge_share",
            rewrite_system_prompt=PROMPT_PATH.read_text(encoding="utf-8"),
        ),
    )

    metadata = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": timestamp,
        "run_id": timestamp,
        "topic": args.topic,
        "angle": args.angle,
        "audience": audience,
        "materials": cards_payload["cards"],
        "article_title": extract_title_and_summary(article)[0],
        "review": {
            "quality_score": review.get("quality_score"),
            "needs_revision": review.get("needs_revision"),
            "safe_to_sync": review.get("safe_to_sync"),
        },
    }
    json_path, md_path, latest_json, latest_md = manifest.run_stage(
        "article_output", lambda: write_knowledge_outputs(article, metadata, timestamp, run_dir)
    )
    review_json_path, review_md_path, review_latest_path = manifest.run_stage(
        "review_output", lambda: write_article_review(review, timestamp, run_dir)
    )
    cover_path = manifest.run_stage("cover_prompt", lambda: write_cover_prompt(article, timestamp, run_dir))
    platform_json_path, platform_md_path, platform_latest_path = manifest.run_stage(
        "platform_pack", lambda: write_platform_pack(article, env, timestamp, run_dir)
    )

    manifest.finish("succeeded")

    log("Knowledge share saved:")
    log(str(md_path))
    log(str(json_path))
    log("Latest knowledge share saved:")
    log(str(latest_md))
    log(str(latest_json))
    log("Article review saved:")
    log(str(review_json_path))
    log(str(review_md_path))
    log(str(review_latest_path))
    log("Cover prompt saved:")
    log(str(cover_path))
    log("Platform pack saved:")
    log(str(platform_json_path))
    log(str(platform_md_path))
    log(str(platform_latest_path))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        if CURRENT_MANIFEST is not None:
            CURRENT_MANIFEST.fail_run(exc)
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
