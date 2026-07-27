import argparse
import html
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from run_manifest import RunManifest

from review_state import write_review_record


CURRENT_MANIFEST: RunManifest | None = None


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "sources.json"
PLATFORMS_PATH = ROOT / "config" / "platforms.json"
ENV_PATH = ROOT / ".env"
OUT_DIR = ROOT / "out"
PROMPT_PATH = ROOT / "prompts" / "daily-tech-intel.md"
COVER_PROMPT_PATH = ROOT / "prompts" / "cover-image.md"
PLATFORM_PROMPT_PATH = ROOT / "prompts" / "platform-pack.md"


@dataclass
class FeedItem:
    title: str
    link: str
    summary: str
    source: str
    category: str
    weight: int
    published: datetime | None
    score: int = 0
    score_breakdown: dict[str, object] = field(default_factory=dict)
    content_type: str = "unknown"
    editorial_score: int = 0
    editorial_breakdown: dict[str, object] = field(default_factory=dict)
    history_penalty: float = 0.0
    history_breakdown: dict[str, object] = field(default_factory=dict)
    content: str = ""


def load_env() -> dict:
    env = {}
    for line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def log(message: str) -> None:
    print(message, flush=True)


def fetch_text(url: str, timeout: int = 20) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": "content-pipeline-mvp/1.0",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalized_url_key(url: str) -> str:
    return url.split("?", 1)[0].split("#", 1)[0].rstrip("/").lower()


def text_tokens(value: str) -> set[str]:
    value = value.lower()
    tokens = set(re.findall(r"[a-z0-9][a-z0-9-]{2,}", value))
    cjk = "".join(re.findall(r"[\u4e00-\u9fff]", value))
    tokens.update(cjk[index:index + 2] for index in range(max(0, len(cjk) - 1)))
    return tokens


def token_similarity(left: str, right: str) -> float:
    left_tokens = text_tokens(left)
    right_tokens = text_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def parse_markdown_title(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value[:25], fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def child_text(node: ET.Element, names: list[str]) -> str:
    for child in list(node):
        local = child.tag.split("}", 1)[-1].lower()
        if local in names and child.text:
            return child.text.strip()
    return ""


def child_link(node: ET.Element) -> str:
    for child in list(node):
        local = child.tag.split("}", 1)[-1].lower()
        if local == "link":
            href = child.attrib.get("href")
            if href:
                return href.strip()
            if child.text:
                return child.text.strip()
    return ""


def parse_feed(xml_text: str, feed: dict) -> list[FeedItem]:
    root = ET.fromstring(xml_text)
    nodes = []
    for node in root.iter():
        local = node.tag.split("}", 1)[-1].lower()
        if local in ("item", "entry"):
            nodes.append(node)

    items = []
    for node in nodes:
        title = clean_text(child_text(node, ["title"]))
        link = child_link(node)
        summary = clean_text(child_text(node, ["description", "summary", "content", "encoded"]))
        published_raw = child_text(node, ["pubdate", "published", "updated", "date"])
        if not title or not link:
            continue
        items.append(
            FeedItem(
                title=title,
                link=link,
                summary=summary,
                source=feed["name"],
                category=feed["category"],
                weight=int(feed.get("weight", 5)),
                published=parse_date(published_raw),
            )
        )
    return items


def score_item(item: FeedItem, keywords: list[str]) -> tuple[int, dict[str, object]]:
    text = f"{item.title} {item.summary}".lower()
    keyword_matches = [kw for kw in keywords if kw.lower() in text]
    keyword_score = len(keyword_matches) * 8
    recency_score = 0
    recency_label = "unknown"
    if item.published:
        age_hours = (datetime.now(timezone.utc) - item.published.astimezone(timezone.utc)).total_seconds() / 3600
        if age_hours <= 36:
            recency_score = 35
            recency_label = "<=36h"
        elif age_hours <= 96:
            recency_score = 20
            recency_label = "<=96h"
        elif age_hours <= 168:
            recency_score = 10
            recency_label = "<=168h"
        else:
            recency_label = ">168h"
    source_score = item.weight * 4
    total = source_score + keyword_score + recency_score
    return total, {
        "source_weight": item.weight,
        "source_score": source_score,
        "keyword_score": keyword_score,
        "keyword_matches": keyword_matches[:12],
        "recency_score": recency_score,
        "recency_label": recency_label,
    }


def load_recent_history(days: int = 7) -> dict[str, object]:
    if not OUT_DIR.exists():
        return {}
    today = time.strftime("%Y-%m-%d")
    run_dirs = sorted(
        [path for path in OUT_DIR.iterdir() if path.is_dir() and path.name <= today],
        key=lambda path: path.name,
        reverse=True,
    )[:days]
    history: dict[str, object] = {
        "urls": set(),
        "titles": [],
        "categories": defaultdict(int),
        "recommended_categories": defaultdict(int),
        "article_titles": [],
        "files": [],
    }

    for run_dir in run_dirs:
        content_pool_files = sorted(run_dir.glob("content-pool-*.json"), reverse=True)
        for path in content_pool_files[:2]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            history["files"].append(str(path.relative_to(ROOT)))
            recommended = data.get("recommended_topic") or {}
            category = str(recommended.get("category") or "")
            if category:
                history["recommended_categories"][category] += 1
            for section in ("selected_for_reader", "content_pool"):
                for item in data.get(section, [])[:20]:
                    title = str(item.get("title") or "")
                    url = str(item.get("url") or "")
                    item_category = str(item.get("category") or "")
                    if title:
                        history["titles"].append(title)
                    if url:
                        history["urls"].add(normalized_url_key(url))
                    if item_category and section == "selected_for_reader":
                        history["categories"][item_category] += 1

        digest_files = sorted(run_dir.glob("daily-digest-*.md"), reverse=True)
        for path in digest_files[:2]:
            try:
                title = parse_markdown_title(path.read_text(encoding="utf-8"))
            except OSError:
                continue
            if title:
                history["article_titles"].append(title)

    return history


def history_penalty_for_item(item: FeedItem, history: dict[str, object]) -> tuple[float, dict[str, object]]:
    if not history:
        return 0.0, {"notes": []}

    penalty = 0.0
    notes = []
    key = normalized_url_key(item.link)
    if key in history.get("urls", set()):
        penalty += 120
        notes.append("最近 7 天已出现过同一链接")

    recent_titles = list(history.get("titles", [])) + list(history.get("article_titles", []))
    best_similarity = 0.0
    best_title = ""
    for title in recent_titles[:80]:
        similarity = token_similarity(item.title, title)
        if similarity > best_similarity:
            best_similarity = similarity
            best_title = title
    if best_similarity >= 0.62:
        penalty += 55
        notes.append(f"标题与近期内容高度相似：{best_title[:80]}")
    elif best_similarity >= 0.46:
        penalty += 28
        notes.append(f"标题与近期内容相近：{best_title[:80]}")

    category_count = int(history.get("categories", {}).get(item.category, 0))
    recommended_count = int(history.get("recommended_categories", {}).get(item.category, 0))
    if recommended_count >= 2:
        penalty += 35
        notes.append(f"{item.category} 最近多次成为建议主线")
    elif recommended_count == 1:
        penalty += 18
        notes.append(f"{item.category} 近期已成为建议主线")
    if category_count >= 6:
        penalty += 14
        notes.append(f"{item.category} 近期入选素材偏多")

    text = f"{item.title} {item.summary}".lower()
    if text_has(text, ["actively exploited", "in the wild", "breach", "incident", "zero-day"]):
        penalty = max(0.0, penalty - 25)
        notes.append("存在强时效安全信号，部分抵消历史降权")

    return penalty, {
        "penalty": round(penalty, 1),
        "best_title_similarity": round(best_similarity, 3),
        "best_title": best_title,
        "recent_category_count": category_count,
        "recent_recommended_category_count": recommended_count,
        "notes": notes,
    }


def apply_history_penalties(items: list[FeedItem], history: dict[str, object]) -> None:
    for item in items:
        item.history_penalty, item.history_breakdown = history_penalty_for_item(item, history)


def text_has(text: str, patterns: list[str]) -> bool:
    text = text.lower()
    for pattern in patterns:
        pattern = pattern.lower()
        if re.fullmatch(r"[a-z0-9][a-z0-9+_. -]*", pattern):
            expression = re.escape(pattern).replace(r"\ ", r"\s+")
            if re.search(rf"(?<![a-z0-9]){expression}(?![a-z0-9])", text):
                return True
        elif pattern in text:
            return True
    return False


UNCONFIRMED_CLAIM_TERMS = [
    "声称",
    "据称",
    "未经证实",
    "未被证实",
    "未确认",
    "未证实",
    "如果属实",
    "if true",
    "claimed",
    "alleged",
    "allegedly",
    "unconfirmed",
]


def has_unconfirmed_claim(value: object) -> bool:
    if isinstance(value, list):
        text = " ".join(str(item) for item in value)
    else:
        text = str(value or "")
    text = text.lower()
    return any(term.lower() in text for term in UNCONFIRMED_CLAIM_TERMS)


def classify_item(item: FeedItem) -> str:
    text = f"{item.title} {item.summary} {item.category} {item.source}".lower()
    if has_unconfirmed_claim(text) and text_has(text, ["unauthorized", "access", "breach", "attack", "compromise", "leak"]):
        return "security_research"
    if text_has(text, ["vibe coding", "vibecoding", "coding agent", "code agent", "ai coding", "ai-assisted coding", "copilot", "cody"]):
        return "ai_coding_workflow"
    if text_has(text, ["workflow automation", "ai workflow", "agent workflow", "multi-agent", "orchestration", "n8n", "zapier"]):
        return "ai_workflow"
    if text_has(text, ["mcp", "model context protocol", "tool use", "computer use", "browser use", "rag", "retrieval", "vector database", "embedding", "eval", "evaluation", "benchmark"]):
        return "ai_engineering"
    if text_has(text, ["prompt injection", "attack", "threat", "breach", "incident", "compromise"]):
        return "security_research"
    if text_has(text, ["cve", "vulnerability", "advisory", "exploit", "ransomware", "malware"]):
        if text_has(text, ["record", "records", "correcting", "reconciling", "unfixed", "will not be fixed"]):
            return "maintenance_notice"
        return "vulnerability_advisory"
    if text_has(text, ["how we built", "architecture", "engineering", "sandbox", "runtime", "postmortem"]):
        return "engineering_practice"
    if text_has(text, ["announce", "announcing", "release", "released", "launch", "introducing", "preview"]):
        return "product_release"
    if item.category.lower() == "research" or text_has(text, ["paper", "arxiv", "research", "study"]):
        return "research"
    if text_has(text, ["github", "open source", "repository", "library", "framework"]):
        return "open_source"
    if text_has(text, ["opinion", "why", "essay", "thoughts", "newsletter"]):
        return "community_analysis"
    return "news"


def editorial_profile(item: FeedItem) -> tuple[int, dict[str, object]]:
    text = f"{item.title} {item.summary} {item.category} {item.source}".lower()
    content_type = classify_item(item)
    base_by_type = {
        "ai_coding_workflow": 76,
        "ai_workflow": 74,
        "ai_engineering": 72,
        "security_research": 72,
        "engineering_practice": 68,
        "open_source": 65,
        "research": 62,
        "product_release": 58,
        "vulnerability_advisory": 56,
        "community_analysis": 52,
        "news": 48,
        "maintenance_notice": 34,
    }
    reader_relevance = 0
    if text_has(text, ["ai", "agent", "llm", "model", "prompt injection", "claude", "openai", "anthropic"]):
        reader_relevance += 18
    if text_has(text, ["vibe coding", "vibecoding", "coding agent", "ai coding", "ai-assisted coding", "copilot", "workflow automation", "ai workflow", "mcp", "rag", "eval"]):
        reader_relevance += 18
    if text_has(text, ["kubernetes", "cloud", "security", "cve", "infrastructure", "developer", "github"]):
        reader_relevance += 12
    if text_has(text, ["how we built", "architecture", "sandbox", "runtime", "tool", "framework"]):
        reader_relevance += 10

    action_value = 0
    if text_has(text, ["mitigation", "configure", "upgrade", "patch", "rbac", "sandbox", "runtime", "api"]):
        action_value += 14
    if text_has(text, ["workflow", "template", "integration", "sdk", "cli", "plugin", "extension", "mcp server", "agent framework", "eval", "benchmark"]):
        action_value += 12
    if text_has(text, ["announce", "release", "how we built", "guide", "best practice"]):
        action_value += 8

    novelty = 0
    if text_has(text, ["first", "new", "introducing", "announcing", "research", "scan", "in the wild"]):
        novelty += 12
    if text_has(text, ["agentic", "computer use", "tool use", "model context protocol", "vibe coding", "workflow automation"]):
        novelty += 8
    if content_type == "maintenance_notice":
        novelty -= 16

    caution_flags = []
    risk_penalty = 0
    if content_type == "maintenance_notice":
        caution_flags.append("维护性通知，不能写成重大事故")
        risk_penalty += 18
    if content_type in ("vulnerability_advisory", "security_research"):
        caution_flags.append("安全类内容需要避免夸大攻击面")
        risk_penalty += 6
    if text_has(text, ["cve", "vulnerability"]) and not text_has(text, ["exploit", "actively exploited", "in the wild"]):
        caution_flags.append("未见主动利用证据，不能暗示攻击爆发")
        risk_penalty += 8
    if text_has(text, ["record", "correcting", "unfixed", "will not be fixed"]):
        caution_flags.append("记录更正/已知风险，不等于新漏洞")
        risk_penalty += 10
    if has_unconfirmed_claim(text):
        caution_flags.append("包含未经确认或单方声称，不能作为主文定论")
        risk_penalty += 30

    score = base_by_type.get(content_type, 45) + reader_relevance + action_value + novelty - risk_penalty
    score = max(0, min(100, score))
    publish_tone = "可作为主线" if score >= 70 else "可作辅助素材" if score >= 50 else "不宜作为主线"
    return score, {
        "content_type": content_type,
        "reader_relevance": reader_relevance,
        "action_value": action_value,
        "novelty": novelty,
        "risk_penalty": risk_penalty,
        "caution_flags": caution_flags,
        "publish_tone": publish_tone,
    }


def final_rank_score(item: FeedItem) -> float:
    return item.score * 0.45 + item.editorial_score * 1.4 - item.history_penalty


def collect_items(config: dict, limit_per_feed: int, feed_timeout: int) -> list[FeedItem]:
    all_items: list[FeedItem] = []
    feeds = config["feeds"]

    def collect_feed(feed: dict) -> tuple[str, list[FeedItem]]:
        try:
            xml_text = fetch_text(feed["url"], timeout=feed_timeout)
            items = parse_feed(xml_text, feed)
            limited = items[:limit_per_feed]
            return f"OK {feed['name']}: {len(limited)}", limited
        except (ET.ParseError, HTTPError, URLError, TimeoutError, ValueError) as exc:
            return f"WARN {feed['name']}: {exc}", []

    max_workers = min(16, max(1, len(feeds)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(collect_feed, feed) for feed in feeds]
        for future in as_completed(futures):
            message, items = future.result()
            log(message)
            all_items.extend(items)

    seen = set()
    unique = []
    for item in all_items:
        key = item.link.split("?")[0].rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    for item in unique:
        item.score, item.score_breakdown = score_item(item, config["keywords"])
        item.editorial_score, item.editorial_breakdown = editorial_profile(item)
        item.content_type = str(item.editorial_breakdown.get("content_type", "unknown"))
    return sorted(unique, key=final_rank_score, reverse=True)


def published_text(item: FeedItem) -> str:
    if not item.published:
        return "unknown"
    return item.published.astimezone(timezone.utc).isoformat()


def selection_notes(item: FeedItem) -> list[str]:
    notes = []
    breakdown = item.score_breakdown
    if int(breakdown.get("source_weight", 0)) >= 8:
        notes.append("高权重信息源")
    recency_score = int(breakdown.get("recency_score", 0))
    if recency_score >= 35:
        notes.append("36 小时内新内容")
    elif recency_score >= 20:
        notes.append("96 小时内仍有时效性")
    keyword_matches = breakdown.get("keyword_matches", [])
    if isinstance(keyword_matches, list) and keyword_matches:
        notes.append("命中重点词：" + "、".join(str(value) for value in keyword_matches[:5]))
    notes.append(f"信息类型：{item.content_type}")
    notes.append(f"发布适配：{item.editorial_breakdown.get('publish_tone', '未知')}")
    caution_flags = item.editorial_breakdown.get("caution_flags", [])
    if isinstance(caution_flags, list) and caution_flags:
        notes.append("风险提醒：" + "、".join(str(value) for value in caution_flags[:2]))
    history_notes = item.history_breakdown.get("notes", [])
    if isinstance(history_notes, list) and history_notes:
        notes.append("历史降权：" + "、".join(str(value) for value in history_notes[:2]))
    if not notes:
        notes.append("基础信号较弱，仅作为候补观察")
    return notes


def item_to_dict(item: FeedItem, rank: int) -> dict:
    summary = item.summary
    if len(summary) > 800:
        summary = summary[:799].rstrip() + "…"
    return {
        "rank": rank,
        "title": item.title,
        "url": item.link,
        "source": item.source,
        "category": item.category,
        "published": published_text(item),
        "score": item.score,
        "score_breakdown": item.score_breakdown,
        "content_type": item.content_type,
        "editorial_score": item.editorial_score,
        "editorial_breakdown": item.editorial_breakdown,
        "history_penalty": round(item.history_penalty, 1),
        "history_breakdown": item.history_breakdown,
        "final_rank_score": round(final_rank_score(item), 1),
        "selection_notes": selection_notes(item),
        "summary": summary,
    }


def build_category_signals(items: list[FeedItem]) -> list[dict]:
    groups: dict[str, list[FeedItem]] = defaultdict(list)
    for item in items:
        groups[item.category].append(item)

    signals = []
    for category, category_items in groups.items():
        ranked_items = sorted(category_items, key=final_rank_score, reverse=True)
        top_scores = [final_rank_score(item) for item in ranked_items[:5]]
        signal_score = sum(top_scores) + min(len(category_items), 5) * 8
        mainline_ready = sum(1 for item in category_items if item.editorial_score >= 70 and final_rank_score(item) >= 100)
        signals.append(
            {
                "category": category,
                "count": len(category_items),
                "signal_score": round(signal_score, 1),
                "top_score": ranked_items[0].score,
                "top_editorial_score": ranked_items[0].editorial_score,
                "mainline_ready": mainline_ready,
                "average_score": round(sum(final_rank_score(item) for item in category_items) / len(category_items), 1),
                "top_items": [item_to_dict(item, index + 1) for index, item in enumerate(ranked_items[:3])],
            }
        )
    return sorted(signals, key=lambda value: (value["signal_score"], value["mainline_ready"]), reverse=True)


def select_items_for_article(items: list[FeedItem], top: int) -> list[FeedItem]:
    preferred = [item for item in items if item.editorial_score >= 55]
    pool = preferred if len(preferred) >= max(3, min(top, 5)) else items
    selected = []
    category_counts: dict[str, int] = defaultdict(int)
    per_category_limit = max(2, min(3, top // 3 + 1))
    for item in sorted(pool, key=final_rank_score, reverse=True):
        if len(selected) >= top:
            break
        if category_counts[item.category] >= per_category_limit and len(pool) - len(selected) > 2:
            continue
        selected.append(item)
        category_counts[item.category] += 1
    return selected


def build_content_pool_payload(
    items: list[FeedItem],
    selected: list[FeedItem],
    timestamp: str,
    pool_size: int,
) -> dict:
    pool_items = items[:pool_size]
    signals = build_category_signals(pool_items)
    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "scoring_rule": {
            "item_score": "source_weight * 4 + recency_score + keyword_matches * 8",
            "editorial_score": "信息类型基准分 + 读者相关性 + 行动价值 + 新知识密度 - 叙事风险扣分",
            "history_penalty": "最近 7 天同链接/相似标题/连续领域主线降权；强时效安全事件可部分抵消",
            "final_rank_score": "item_score * 0.45 + editorial_score * 1.4 - history_penalty",
            "recency_score": {
                "<=36h": 35,
                "<=96h": 20,
                "<=168h": 10,
                ">168h_or_unknown": 0,
            },
            "content_types": [
                "ai_coding_workflow",
                "ai_workflow",
                "ai_engineering",
                "security_research",
                "engineering_practice",
                "open_source",
                "research",
                "product_release",
                "vulnerability_advisory",
                "maintenance_notice",
                "community_analysis",
                "news",
            ],
            "category_signal_score": "sum(top_5_final_rank_scores_in_category) + min(category_count, 5) * 8",
            "editorial_policy": "RSS 分数只代表信息强度；发布适配分优先奖励 AI coding、Agent/workflow、MCP/RAG/eval、工程实践等高行动价值主题，同时降低维护性通知、无主动利用证据的漏洞公告、未经确认的单方声称和容易被夸大的选题权重；历史降权会压低连续重复主题。人工审核仍是最后一关。",
        },
        "collected_count": len(items),
        "pool_size": len(pool_items),
        "selected_for_reader_count": len(selected),
        "recommended_topic": signals[0] if signals else None,
        "category_signals": signals,
        "selected_for_reader": [item_to_dict(item, index + 1) for index, item in enumerate(selected)],
        "content_pool": [item_to_dict(item, index + 1) for index, item in enumerate(pool_items)],
        "timestamp": timestamp,
    }


def content_pool_to_markdown(payload: dict) -> str:
    rule = payload["scoring_rule"]
    lines = [
        "# 今日内容池",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- RSS 去重后候选：{payload['collected_count']} 条",
        f"- 展示内容池：Top {payload['pool_size']} 条",
        f"- 送入 Jina Reader / 成文候选：Top {payload['selected_for_reader_count']} 条",
        "",
        "## 选择规则",
        "",
        f"- 单篇分数：`{rule['item_score']}`",
        f"- 发布适配分：`{rule['editorial_score']}`",
        f"- 历史降权：`{rule['history_penalty']}`",
        f"- 最终排序分：`{rule['final_rank_score']}`",
        "- 新鲜度：36 小时内 +35，96 小时内 +20，168 小时内 +10。",
        f"- 领域信号：`{rule['category_signal_score']}`",
        f"- 编辑原则：{rule['editorial_policy']}",
        "",
    ]

    recommended = payload.get("recommended_topic")
    if recommended:
        lines.extend(
            [
                "## RSS 初筛建议主线",
                "",
                f"- 领域：{recommended['category']}",
                f"- 领域信号分：{recommended['signal_score']}",
                f"- 入池数量：{recommended['count']} 条",
                f"- 最高单篇分：{recommended['top_score']}",
                f"- 可作主线素材数：{recommended['mainline_ready']} 条",
                "",
                "这个建议来自 RSS 阶段的结构化信号：同一领域是否有多条高分内容、是否来自高权重来源、是否足够新、是否命中账号重点方向，以及是否具备发布适配性。最终文章仍应由模型和人工审核判断主线是否成立。",
                "",
            ]
        )

    lines.extend(["## 领域信号排行", ""])
    for signal in payload["category_signals"]:
        lines.append(
            f"- {signal['category']}：信号 {signal['signal_score']}，{signal['count']} 条，可作主线 {signal['mainline_ready']} 条，最高 RSS {signal['top_score']}，最高适配 {signal['top_editorial_score']}，均分 {signal['average_score']}"
        )
    lines.append("")

    lines.extend(["## 入选成文候选", ""])
    for item in payload["selected_for_reader"]:
        notes = "；".join(item["selection_notes"])
        lines.extend(
            [
                f"### {item['rank']}. {item['title']}",
                "",
                f"- 来源：{item['source']} / {item['category']}",
                f"- 信息类型：{item['content_type']}；发布适配分：{item['editorial_score']}；历史降权：{item['history_penalty']}；最终排序分：{item['final_rank_score']}",
                f"- 发布时间：{item['published']}",
                f"- 分数：{item['score']}（来源 {item['score_breakdown']['source_score']} + 新鲜度 {item['score_breakdown']['recency_score']} + 关键词 {item['score_breakdown']['keyword_score']}）",
                f"- 入选理由：{notes}",
                f"- 链接：{item['url']}",
                "",
            ]
        )

    lines.extend(["## 完整内容池", ""])
    for item in payload["content_pool"]:
        notes = "；".join(item["selection_notes"])
        lines.append(
            f"{item['rank']}. [{item['title']}]({item['url']}) - {item['source']} / {item['category']} / RSS {item['score']} / 适配 {item['editorial_score']} / 历史降权 {item['history_penalty']} / {item['content_type']} / {notes}"
        )
    lines.append("")
    return "\n".join(lines)


def write_content_pool(
    items: list[FeedItem],
    selected: list[FeedItem],
    timestamp: str,
    run_dir: Path,
    pool_size: int,
) -> tuple[dict, Path, Path, Path]:
    payload = build_content_pool_payload(items, selected, timestamp, pool_size)
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    md_text = content_pool_to_markdown(payload)

    json_path = run_dir / f"content-pool-{timestamp}.json"
    md_path = run_dir / f"content-pool-{timestamp}.md"
    latest_json = OUT_DIR / "content-pool-latest.json"
    latest_md = OUT_DIR / "content-pool-latest.md"

    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    return payload, json_path, md_path, latest_md


def enrich_with_reader(items: list[FeedItem], env: dict, reader_timeout: int) -> None:
    reader_base = env.get("JINA_READER_BASE_URL", "https://r.jina.ai/").rstrip("/")
    for index, item in enumerate(items, 1):
        try:
            log(f"Reading {index}/{len(items)}: {item.title[:70]}")
            content = fetch_text(f"{reader_base}/{item.link}", timeout=reader_timeout)
            content = content.replace("\x00", "")
            item.content = content[:5000]
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            log(f"WARN reader failed: {item.link} {exc}")
            item.content = item.summary[:1200]


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[。！？.!?])\s+", text)
    return [part.strip() for part in parts if len(part.strip()) >= 24]


def extract_evidence_sentences(item: FeedItem, max_count: int = 5) -> list[str]:
    text = item.content or item.summary
    sentences = split_sentences(text)
    priority_patterns = [
        r"\d+(?:\.\d+)?\s*%",
        r"\d+(?:\.\d+)?\s*个百分点",
        r"\b20\d{2}[-年]\d{1,2}",
        r"\b[A-Z][A-Za-z0-9.-]*(?:\s+\d+(?:\.\d+)*)?\b",
        r"\b(CVE-\d{4}-\d+|DPO|SFT|RLHF|MCP|SQL|NoSQL|API|LLM|Agent)\b",
    ]
    scored = []
    for index, sentence in enumerate(sentences[:80]):
        score = 0
        for pattern in priority_patterns:
            if re.search(pattern, sentence):
                score += 2
        if any(word in sentence.lower() for word in ["announce", "released", "improve", "accuracy", "benchmark", "evaluation", "安全", "发布", "提升", "模型", "评估"]):
            score += 1
        scored.append((score, index, sentence))
    scored.sort(key=lambda value: (-value[0], value[1]))
    selected = [sentence for score, _, sentence in scored if score > 0][:max_count]
    if len(selected) < 2:
        selected.extend(sentence for sentence in sentences[:max_count] if sentence not in selected)
    return selected[:max_count]


def build_fact_cards(items: list[FeedItem], timestamp: str) -> dict:
    cards = []
    for index, item in enumerate(items, 1):
        evidence = extract_evidence_sentences(item)
        numeric_claims = []
        evidence_text = " ".join(evidence)
        numeric_claims.extend(re.findall(r"\d+(?:\.\d+)?\s*%", evidence_text))
        numeric_claims.extend(re.findall(r"\d+(?:\.\d+)?\s*个百分点", evidence_text))
        numeric_claims.extend(re.findall(r"\d+(?:\.\d+)?\s*(?:B|b|M|m)\b", evidence_text))
        numeric_claims = list(dict.fromkeys(claim.strip() for claim in numeric_claims))
        cards.append({
            "rank": index,
            "title": item.title,
            "source": item.source,
            "category": item.category,
            "content_type": item.content_type,
            "url": item.link,
            "published": published_text(item),
            "editorial_score": item.editorial_score,
            "history_penalty": round(item.history_penalty, 1),
            "final_rank_score": round(final_rank_score(item), 1),
            "facts": evidence,
            "numeric_claims": numeric_claims,
            "cannot_infer": [
                "不能把社区讨论写成已验证行业结论",
                "不能使用来源摘录中不存在的日期、百分比、模型名或评测数字",
                "不能把弱相关来源硬串成同一事件",
            ],
        })
    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": timestamp,
        "cards": cards,
    }


def fact_cards_to_markdown(payload: dict) -> str:
    lines = [
        "# 事实卡片",
        "",
        f"- 生成时间：{payload['generated_at']}",
        "",
    ]
    for card in payload["cards"]:
        lines.extend([
            f"## {card['rank']}. {card['title']}",
            "",
            f"- 来源：{card['source']} / {card['category']} / {card['content_type']}",
            f"- 链接：{card['url']}",
            f"- 发布时间：{card['published']}",
            f"- 发布适配分：{card['editorial_score']}；历史降权：{card['history_penalty']}；最终排序分：{card['final_rank_score']}",
            "- 可用事实：",
        ])
        for fact in card["facts"]:
            lines.append(f"  - {fact}")
        if card["numeric_claims"]:
            lines.append("- 需核对数字：" + "、".join(card["numeric_claims"]))
        lines.append("- 不可推断：")
        for item in card["cannot_infer"]:
            lines.append(f"  - {item}")
        lines.append("")
    return "\n".join(lines)


def write_fact_cards(payload: dict, timestamp: str, run_dir: Path) -> tuple[Path, Path, Path]:
    json_path = run_dir / f"fact-cards-{timestamp}.json"
    md_path = run_dir / f"fact-cards-{timestamp}.md"
    latest_json = OUT_DIR / "fact-cards-latest.json"
    latest_md = OUT_DIR / "fact-cards-latest.md"
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    md_text = fact_cards_to_markdown(payload)
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    return json_path, md_path, latest_md


def deepseek_chat(env: dict, prompt: str, timeout: int = 180, system_prompt: str | None = None) -> str:
    base_url = env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = env.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
    api_key = env.get("DEEPSEEK_API_KEY", "")
    if not api_key or api_key == "sk-your-deepseek-key":
        raise RuntimeError("Please fill DEEPSEEK_API_KEY in .env first.")

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt or PROMPT_PATH.read_text(encoding="utf-8")},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = Request(
        f"{base_url}/chat/completions",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"]


def build_article_prompt(
    items: list[FeedItem],
    profile: dict,
    content_pool: dict | None = None,
    fact_cards: dict | None = None,
    topic_candidates: dict | None = None,
) -> str:
    if content_pool:
        category_summary = "\n".join(
            f"- {signal['category']}: {signal['count']} 条，领域信号 {signal['signal_score']}，可作主线 {signal['mainline_ready']} 条，最高适配 {signal['top_editorial_score']}"
            for signal in content_pool["category_signals"][:8]
        )
        recommended = content_pool.get("recommended_topic")
        recommended_topic = (
            f"{recommended['category']}（领域信号 {recommended['signal_score']}，可作主线 {recommended['mainline_ready']} 条）"
            if recommended
            else "无"
        )
        pool_summary = "\n".join(
            f"- #{item['rank']} {item['title']} | {item['source']} | {item['category']} | {item['content_type']} | RSS {item['score']} | 适配 {item['editorial_score']} | 历史降权 {item.get('history_penalty', 0)} | 风险：{';'.join(item['editorial_breakdown'].get('caution_flags', [])[:2]) or '无'}"
            for item in content_pool["content_pool"][:20]
        )
    else:
        signals = build_category_signals(items)
        category_summary = "\n".join(
            f"- {signal['category']}: {signal['count']} 条，领域信号 {signal['signal_score']}，最高单篇 {signal['top_score']}"
            for signal in signals
        )
        recommended_topic = signals[0]["category"] if signals else "无"
        pool_summary = ""

    selected_candidate = (topic_candidates or {}).get("gate", {}).get("selected_candidate")
    selected_candidate_text = json.dumps(selected_candidate, ensure_ascii=False, indent=2) if selected_candidate else "无"
    gate = (topic_candidates or {}).get("gate", {})
    gate_mode = str(gate.get("mode", "FULL_ARTICLE") or "FULL_ARTICLE")
    if gate_mode == "SINGLE_SOURCE_OBSERVATION":
        writing_mode_instruction = """本次写作模式：SINGLE_SOURCE_OBSERVATION。
- 这是“单一强来源观察”，不是完整行业主线文章。
- 标题和正文必须明确降低语气：可以写“一个信号”“一次实验/一篇论文/一个案例说明了什么”，不要写成“行业已经全面转向”。
- 文章长度建议 800-1200 字；重点写清：来源说了什么、为什么值得关注、它不能说明什么、读者可以观察什么。
- 必须显式保留不确定性：如果只有一个来源，不得用“证明”“标志着”“全面爆发”等定论表达。"""
    elif gate_mode == "SHORT_OBSERVATION":
        writing_mode_instruction = """本次写作模式：SHORT_OBSERVATION。
- 今天没有强主线，只生成“技术短观察”，不要包装成深度主文。
- 文章长度建议 500-900 字；标题可以带“短观察”“一个信号”“值得留意”之类的限定。
- 只写一个候选，不要为了凑篇幅硬串多个弱相关来源。
- 结尾给出轻量行动建议或观察清单，不要输出宏大结论。"""
    else:
        writing_mode_instruction = """本次写作模式：FULL_ARTICLE。
- 可以写成完整主文，但仍需围绕一个明确主线展开。
- 文章长度建议 1200-1800 字；必须用多来源事实支撑标题、开头和主要判断。"""
    fact_cards_text = json.dumps((fact_cards or {}).get("cards", [])[:8], ensure_ascii=False, indent=2)

    blocks = []
    for i, item in enumerate(items, 1):
        published = item.published.isoformat() if item.published else "unknown"
        blocks.append(
            f"""[{i}]
Title: {item.title}
Source: {item.source}
Category: {item.category}
Published: {published}
Score: {item.score}
EditorialScore: {item.editorial_score}
HistoryPenalty: {item.history_penalty}
FinalRankScore: {round(final_rank_score(item), 1)}
URL: {item.link}
Summary: {item.summary}
Content excerpt:
{item.content}
"""
        )

    return f"""请基于下面的技术信息源，写一篇中文技术情报日报。

账号定位：{profile['name']}
目标读者：{profile['audience']}
重点方向：{", ".join(profile['focus'])}

候选领域信号强度：
{category_summary}

RSS 初筛建议主线：
{recommended_topic}

今日内容池摘要：
{pool_summary}

选题闸门通过的候选：
{selected_candidate_text}

写作模式：
{writing_mode_instruction}

事实卡片（正文只能使用这些事实和候选素材正文摘录，不得新增事实）：
{fact_cards_text}

要求：
- 不是逐条翻译，也不是信息拼盘，而是做编辑筛选和判断。
- 必须围绕“选题闸门通过的候选”写；如果候选为空，不要写主文。
- 必须严格遵守“写作模式”：FULL_ARTICLE 写主文，SINGLE_SOURCE_OBSERVATION 写谨慎单来源观察，SHORT_OBSERVATION 写短观察。
- 每个事实、日期、数字、模型名和来源链接都必须能在事实卡片或候选素材正文摘录中找到支持。
- 不要硬串弱相关来源；旁证来源必须直接支撑同一主线。
- 你必须先判断“今天最值得写的一个主线主题”，但判断过程是内部编辑工作，不要写进发布正文。
- 主线必须有“问题意识”：围绕一个可回答的问题写，例如“AI coding 正在改变哪一段开发流程”“这个 workflow 为什么现在值得试”“这项安全更新会影响哪些工程决策”。
- AI coding / vibe coding / workflow 类文章必须写清楚具体工作流变化：原来怎么做、现在多了什么能力、适合谁、不适合谁、读者下一步如何小范围验证。
- AI 工程化类文章优先解释 MCP、RAG、eval、tool use、browser/computer use、部署成本、观测和安全边界，不要只写模型发布新闻。
- 如果主题只是普通产品更新，必须降级为短观察或跳过；只有当它改变开发流程、平台生态或风险边界时才写成主文。
- 正文必须直接从一级标题开始，格式为“# 具体标题”。
- 不要输出“好的”“以下是”“主编决策说明”“RSS 初筛建议主线”“我的最终选择”“为何不采用 RSS 建议”“结论：今天的文章将围绕”等内部说明。
- 优先选择“发布适配分”高且 caution_flags 少的素材作为主线；RSS 分高但标记为 maintenance_notice 的素材只能写成“记录更正/配置提醒”，不能写成重大事故。
- 如果素材或领域带有较高“历史降权”，说明最近几天已经写过或高度相似；除非存在明确重大更新，否则不要继续把它作为今日主线。
- 必须先识别信息类型：安全事故、漏洞公告、工程实践、产品发布、研究论文、社区讨论、维护性通知。不同类型要用不同语气。
- 如果是维护性通知或漏洞记录更正，禁止使用“爆发”“全网攻击”“全面告警”“官方承认”“永远不会修复”等强叙事表达。
- 安全类内容只有在来源明确说明 actively exploited / in the wild / breach / incident 时，才可以写成攻击事件。
- 只围绕这个主线展开，其他无关领域可以完全不写。
- 如果 AI/Agent 最有价值就写 AI/Agent；如果安全事件最有价值就写安全；如果开源项目最有价值就写开源项目。
- 每条信息要直接说明“意义是什么”。
- 开头要有吸引力：可以用具体问题、反常识判断、趋势冲突、机会窗口或风险提醒。
- 标题要具体，有信息增量，不要泛泛写“今日技术情报”。
- 正文不需要覆盖所有候选素材，只引用能支撑主线的素材。
- 如果要提到其他领域，只能作为“旁证”或“次要观察”，不要并列展开。
- 不要编造数据，不确定就写不确定。
- 文章适合知乎、稀土掘金、B站、CSDN、抖音、小红书等平台发布。
- 最后保留来源链接，只能使用候选素材中提供的 URL，不要推测、补写或改造 URL。

候选素材：

{chr(10).join(blocks)}
"""


def extract_title_and_summary(article: str) -> tuple[str, str]:
    title = "技术情报日报"
    for line in article.splitlines():
        line = line.strip()
        if line.startswith("# "):
            title = line[2:].strip()
            break
    body = re.sub(r"#+\s*", "", article)
    body = re.sub(r"\s+", " ", body).strip()
    return title, body[:500]


def sanitize_article(article: str) -> str:
    article = article.replace("\r\n", "\n").replace("\r", "\n").strip()
    article = re.sub(r"^```(?:markdown)?\s*", "", article, flags=re.I)
    article = re.sub(r"\s*```$", "", article).strip()

    lines = article.splitlines()
    title_index = None
    title_text = ""
    for index, line in enumerate(lines):
        stripped = line.strip()
        title_match = re.match(r"^(?:\*\*)?标题[:：](?:\*\*)?\s*(.+)$", stripped)
        if title_match:
            title_index = index
            title_text = re.sub(r"^\*\*|\*\*$", "", title_match.group(1)).strip()
            break
        heading_match = re.match(r"^#\s+(.+)$", stripped)
        if heading_match:
            heading = heading_match.group(1).strip()
            if not re.search(r"主编决策|RSS|初筛|最终选择|技术情报日报", heading, flags=re.I):
                title_index = index
                title_text = heading
                break

    if title_index is not None:
        remaining = lines[title_index + 1 :]
        if title_text:
            article = "\n".join([f"# {title_text}", "", *remaining]).strip()
        else:
            article = "\n".join(lines[title_index:]).strip()

    article = re.sub(
        r"(?s)^.*?(?=^#\s+)",
        "",
        article,
        count=1,
        flags=re.M,
    ).strip()
    article = re.sub(r"(?m)^#{2,6}\s*技术情报日报\s*$\n*", "", article).strip()
    article = re.sub(r"(?m)^\*\*开头(?:（[^）]*）)?\*\*\s*$\n*", "", article).strip()
    article = re.sub(r"(?m)^#{2,6}\s*开头(?:（[^）]*）)?\s*$\n*", "", article).strip()
    article = re.sub(r"(?m)^\s*[-—]{3,}\s*$\n*", "", article).strip()
    return article


RISKY_TERMS = [
    "全面告警",
    "永远不会修复",
    "永无补丁",
    "永不修复",
    "官方承认",
    "全网攻击",
    "开始越狱",
    "攻击爆发",
    "重大事故",
]


RELATIVE_DATE_TERMS = ["今天", "明天", "昨天", "下周", "下周一", "本周", "上周", "近日", "近期", "最近"]


def deterministic_article_checks(article: str) -> list[dict]:
    findings = []
    if not re.search(r"(?m)^#\s+\S+", article):
        findings.append({"severity": "high", "issue": "正文没有一级标题", "suggestion": "以 # 具体标题 开始正文"})
    title_match = re.search(r"(?m)^#\s+(.+)$", article)
    title = title_match.group(1).strip() if title_match else ""
    if title and has_unconfirmed_claim(title) and any(term in title for term in ["攻破", "突破", "入侵", "泄露", "攻击", "安全事件"]):
        findings.append({
            "severity": "high",
            "issue": "标题把未经确认的安全/入侵类声称作为主要卖点",
            "suggestion": "改成以可验证主题为主线，例如预部署验证、权限边界或风险治理；未经确认的声称只能在正文中作为谨慎引子。",
        })
    for term in RISKY_TERMS:
        if term in article:
            findings.append({
                "severity": "medium",
                "issue": f"出现高风险强词：{term}",
                "suggestion": "除非来源明确支持，否则改为更谨慎的事实表达",
            })
    for term in RELATIVE_DATE_TERMS:
        if term in article:
            findings.append({
                "severity": "medium",
                "issue": f"出现相对日期：{term}",
                "suggestion": "改为 YYYY年M月D日 等绝对日期",
            })
    for term in ["主编决策说明", "RSS 初筛建议主线", "我的最终选择", "以下是", "好的，作为"]:
        if term in article:
            findings.append({
                "severity": "high",
                "issue": f"出现内部编辑说明：{term}",
                "suggestion": "删除内部说明，只保留面向读者的正文",
            })
    if "URL根据原文推测" in article or "根据原文推测" in article:
        findings.append({
            "severity": "high",
            "issue": "存在推测来源链接说明",
            "suggestion": "只能使用候选素材中的原始 URL",
        })
    numeric_claims = []
    numeric_claims.extend(re.findall(r"\d+(?:\.\d+)?\s*%", article))
    numeric_claims.extend(re.findall(r"\d+(?:\.\d+)?\s*个百分点", article))
    numeric_claims.extend(re.findall(r"\d+(?:\.\d+)?\s*(?:B|b|M|m)\b", article))
    if numeric_claims:
        unique_claims = list(dict.fromkeys(value.strip() for value in numeric_claims))[:8]
        findings.append({
            "severity": "low",
            "issue": "文章包含需要来源核对的数字：" + "、".join(unique_claims),
            "suggestion": "发布前必须逐项确认这些数字与来源原文一致；若来源证据不明确，删除或改成不含具体数字的表述。",
        })
    return findings


def source_evidence_blocks(items: list[FeedItem], limit: int = 8, excerpt_len: int = 2400) -> str:
    blocks = []
    for index, item in enumerate(items[:limit], 1):
        excerpt = item.content or item.summary
        excerpt = re.sub(r"\s+", " ", excerpt).strip()
        if len(excerpt) > excerpt_len:
            excerpt = excerpt[: excerpt_len - 1].rstrip() + "…"
        blocks.append(
            f"""[{index}]
Title: {item.title}
Source: {item.source}
Category: {item.category}
Type: {item.content_type}
URL: {item.link}
Summary: {item.summary}
Source excerpt:
{excerpt}
"""
        )
    return "\n".join(blocks)


def build_topic_candidate_prompt(fact_cards: dict, profile: dict) -> str:
    cards_text = json.dumps(fact_cards["cards"][:10], ensure_ascii=False, indent=2)
    return f"""请基于下面的事实卡片，先做选题判断，不要写文章。

账号定位：{profile['name']}
目标读者：{profile['audience']}
重点方向：{", ".join(profile['focus'])}

硬性标准：
- A：至少 2 个强相关高质量来源支撑同一主线，行动价值明确，事实证据足够支撑标题。
- B：1 个强主来源 + 1 个明确旁证，适合成文但需谨慎。
- C：有观察价值，但素材薄、旁证弱或更适合短观察。
- REJECT：弱素材、硬串来源、普通产品更新/维护公告、只有社区讨论、事实证据不足，不建议写主文。
- 如果核心事实包含“声称/据称/if true/claimed/alleged/未经证实/未确认”，不得评为 A/B，也不得 recommended_action=WRITE；最多评为 C + SHORT_OBSERVATION。

优先主题池：
- AI coding / vibe coding：coding agent、AI IDE、Copilot/Cody、代码生成工作流、人机协作开发方式。
- Agent workflow：workflow automation、multi-agent orchestration、n8n/Zapier 类自动化、Agent 与业务流程集成。
- AI 工程化：MCP、tool use、computer/browser use、RAG、向量检索、eval/benchmark、模型部署和成本优化。
- 开发者基础设施：CI/CD、云原生、数据库、运行时、框架、可观测性、安全沙箱。
- 安全与风险：真实攻击事件、主动利用漏洞、AI 安全、供应链安全。安全题必须比其他题更严格核验证据。

高质量选题必须至少满足以下 2 项：
- 有明确变化：发布、实验结果、真实案例、架构调整、生态趋势或风险升级。
- 有行动价值：读者看完能调整工具、流程、架构、风控或学习路线。
- 有冲突/反差：新工具改变旧工作流，模型能力与工程约束冲突，安全收益与风险同时出现。
- 有足够证据：标题和核心判断能被事实卡片直接支持。

特别注意：
- HN/社区讨论只能作线索，不能单独支撑主文。
- 产品 changelog 默认不作主文，除非有明确重大影响。
- 旁证来源必须直接支撑同一主线，不能只是“同一天出现”。
- 候选主线不得使用事实卡片之外的日期、数字、模型名、评测结果。
- 不要因为 AI 题更热门就自动选择 AI；AI 题同样需要具体变化、可验证事实和读者行动价值。
- 未经确认的传闻、单方声称、contributed piece 中的二手描述，只能作为引子或风险提醒；文章主线必须放在可验证的论文、官方公告、工程实践或多来源证据上。
- 不要把“声称发生的安全事件”写成“真实入侵案例”；除非来源提供官方确认、独立调查或可核验证据。

只输出 JSON：
{{
  "overall_decision": "WRITE|NO_STRONG_TOPIC",
  "summary": "一句话说明今天是否值得写主文",
  "candidates": [
    {{
      "grade": "A|B|C|REJECT",
      "topic": "候选主题",
      "working_title": "候选标题",
      "core_facts": ["事实1", "事实2"],
      "supporting_sources": ["来源标题或URL"],
      "why_worth_writing": "为什么值得写",
      "why_not": "为什么可能不值得写",
      "publishing_risks": ["风险1"],
      "recommended_action": "WRITE|SHORT_OBSERVATION|SKIP",
      "evidence_quality": "verified_or_bounded|mixed_unconfirmed|weak"
    }}
  ]
}}

事实卡片：
{cards_text}
"""


def fallback_topic_candidates(fact_cards: dict) -> dict:
    cards = fact_cards.get("cards", [])
    groups: dict[str, list[dict]] = defaultdict(list)
    for card in cards:
        groups[str(card.get("category", "unknown"))].append(card)

    candidates = []
    for category, category_cards in sorted(
        groups.items(),
        key=lambda pair: sum(float(card.get("final_rank_score", 0)) for card in pair[1]),
        reverse=True,
    )[:3]:
        strong = [card for card in category_cards if float(card.get("editorial_score", 0)) >= 70]
        if len(strong) >= 2:
            grade = "B"
            action = "WRITE"
        elif len(strong) == 1 and strong[0].get("source") not in ("Hacker News Front Page", "Hacker News Newest"):
            grade = "C"
            action = "SHORT_OBSERVATION"
        else:
            grade = "REJECT"
            action = "SKIP"
        candidates.append({
            "grade": grade,
            "topic": f"{category} 方向的技术信号",
            "working_title": f"{category} 今日技术观察",
            "core_facts": [fact for card in strong[:2] for fact in card.get("facts", [])[:1]],
            "supporting_sources": [card.get("title", "") for card in strong[:3]],
            "why_worth_writing": "该方向有多个发布适配分较高的素材。" if strong else "暂无强素材。",
            "why_not": "需要人工确认这些来源是否真正支撑同一主线，避免硬串。",
            "publishing_risks": ["自动候选，未经过模型语义判断"],
            "recommended_action": action,
        })
    overall = "WRITE" if any(candidate["grade"] in ("A", "B") for candidate in candidates) else "NO_STRONG_TOPIC"
    return {
        "overall_decision": overall,
        "summary": "自动兜底选题候选。",
        "candidates": candidates,
    }


def normalize_topic_candidates(raw: str, fact_cards: dict) -> dict:
    try:
        data = extract_json_object(raw)
    except Exception:
        data = fallback_topic_candidates(fact_cards)
    candidates = data.get("candidates", [])
    if not isinstance(candidates, list):
        candidates = []
    normalized = []
    for candidate in candidates[:5]:
        if not isinstance(candidate, dict):
            continue
        grade = str(candidate.get("grade", "REJECT")).upper()
        if grade not in ("A", "B", "C", "REJECT"):
            grade = "REJECT"
        action = str(candidate.get("recommended_action", "")).upper()
        if action not in ("WRITE", "SHORT_OBSERVATION", "SKIP"):
            action = "WRITE" if grade in ("A", "B") else "SHORT_OBSERVATION" if grade == "C" else "SKIP"
        core_facts = candidate.get("core_facts", []) if isinstance(candidate.get("core_facts", []), list) else []
        supporting_sources = candidate.get("supporting_sources", []) if isinstance(candidate.get("supporting_sources", []), list) else []
        publishing_risks = candidate.get("publishing_risks", []) if isinstance(candidate.get("publishing_risks", []), list) else []
        working_title = str(candidate.get("working_title", "")).strip()
        unconfirmed_core_claim = (
            has_unconfirmed_claim(core_facts)
            or has_unconfirmed_claim(working_title)
            or has_unconfirmed_claim(publishing_risks)
        )
        evidence_quality = "mixed_unconfirmed" if unconfirmed_core_claim else "verified_or_bounded"
        if unconfirmed_core_claim and action == "WRITE":
            grade = "C"
            action = "SHORT_OBSERVATION"
            if "存在未经确认的核心事实，只能作为风险观察或引子，不能作为主文定论。" not in publishing_risks:
                publishing_risks.append("存在未经确认的核心事实，只能作为风险观察或引子，不能作为主文定论。")
        normalized.append({
            "grade": grade,
            "topic": str(candidate.get("topic", "")).strip(),
            "working_title": working_title,
            "core_facts": core_facts,
            "supporting_sources": supporting_sources,
            "why_worth_writing": str(candidate.get("why_worth_writing", "")).strip(),
            "why_not": str(candidate.get("why_not", "")).strip(),
            "publishing_risks": publishing_risks,
            "recommended_action": action,
            "evidence_quality": evidence_quality,
        })
    data["candidates"] = normalized
    has_write = any(
        candidate["grade"] in ("A", "B") and candidate["recommended_action"] == "WRITE"
        for candidate in normalized
    )
    has_short = any(
        candidate["grade"] == "C" or candidate["recommended_action"] == "SHORT_OBSERVATION"
        for candidate in normalized
    )
    data["overall_decision"] = "WRITE" if has_write else "SHORT_OBSERVATION" if has_short else "NO_STRONG_TOPIC"
    data.setdefault("summary", "")
    data["gate"] = evaluate_topic_gate(data)
    return data


def evaluate_topic_gate(topic_candidates: dict) -> dict:
    candidates = topic_candidates.get("candidates", [])
    write_candidates = [
        candidate for candidate in candidates
        if candidate.get("grade") in ("A", "B") and candidate.get("recommended_action") == "WRITE"
    ]
    if write_candidates:
        selected = write_candidates[0]
        source_count = len(selected.get("supporting_sources", []))
        if source_count < 2:
            return {
                "decision": "WRITE",
                "mode": "SINGLE_SOURCE_OBSERVATION",
                "reason": "存在 B 级候选，但支撑来源不足两个；生成谨慎的单来源观察，不写成行业定论。",
                "selected_candidate": selected,
            }
        return {
            "decision": "WRITE",
            "mode": "FULL_ARTICLE",
            "reason": "存在通过 A/B 门槛且有多来源支撑的候选选题。",
            "selected_candidate": selected,
        }

    short_candidates = [
        candidate for candidate in candidates
        if candidate.get("grade") == "C" or candidate.get("recommended_action") == "SHORT_OBSERVATION"
    ]
    if short_candidates:
        return {
            "decision": "WRITE_SHORT",
            "mode": "SHORT_OBSERVATION",
            "reason": "没有强主线，但存在可写的 C 级/短观察候选；生成轻量观察，不包装成正式主文。",
            "selected_candidate": short_candidates[0],
        }

    return {
        "decision": "REJECT",
        "mode": "NO_ARTICLE",
        "reason": "没有 A/B 级候选，也没有适合短观察的候选。",
        "selected_candidate": None,
    }


def generate_topic_candidates(env: dict, fact_cards: dict, profile: dict, timestamp: str, run_dir: Path) -> tuple[dict, Path, Path, Path]:
    log("Generating topic candidates with DeepSeek...")
    try:
        raw = deepseek_chat(
            env,
            build_topic_candidate_prompt(fact_cards, profile),
            timeout=180,
            system_prompt="你是严格的中文技术内容选题主编。你只输出 JSON，不输出 Markdown。",
        )
    except Exception as exc:
        log(f"WARN topic candidate generation failed: {exc}")
        raw = json.dumps(fallback_topic_candidates(fact_cards), ensure_ascii=False)
    payload = normalize_topic_candidates(raw, fact_cards)
    json_path = run_dir / f"topic-candidates-{timestamp}.json"
    md_path = run_dir / f"topic-candidates-{timestamp}.md"
    latest_json = OUT_DIR / "topic-candidates-latest.json"
    latest_md = OUT_DIR / "topic-candidates-latest.md"
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    md_text = topic_candidates_to_markdown(payload)
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    return payload, json_path, md_path, latest_md


def topic_candidates_to_markdown(payload: dict) -> str:
    gate = payload.get("gate", {})
    lines = [
        "# 选题候选",
        "",
        f"- 总体决策：{payload.get('overall_decision', '')}",
        f"- 闸门：{gate.get('decision', '')}",
        f"- 原因：{gate.get('reason', '')}",
        f"- 总评：{payload.get('summary', '')}",
        "",
    ]
    for index, candidate in enumerate(payload.get("candidates", []), 1):
        lines.extend([
            f"## {index}. [{candidate.get('grade')}] {candidate.get('topic')}",
            "",
            f"- 候选标题：{candidate.get('working_title')}",
            f"- 建议动作：{candidate.get('recommended_action')}",
            f"- 证据质量：{candidate.get('evidence_quality', 'unknown')}",
            f"- 为什么值得写：{candidate.get('why_worth_writing')}",
            f"- 为什么可能不值得写：{candidate.get('why_not')}",
            "- 支撑来源：",
        ])
        for source in candidate.get("supporting_sources", []):
            lines.append(f"  - {source}")
        lines.append("- 核心事实：")
        for fact in candidate.get("core_facts", []):
            lines.append(f"  - {fact}")
        lines.append("- 发布风险：")
        risks = candidate.get("publishing_risks", [])
        if not risks:
            lines.append("  - 无")
        for risk in risks:
            lines.append(f"  - {risk}")
        lines.append("")
    return "\n".join(lines)


def build_article_review_prompt(
    article: str,
    content_pool: dict,
    source_items: list[FeedItem],
    content_kind: str = "daily_digest",
) -> str:
    selected_summary = "\n".join(
        f"- {item['title']} | {item['source']} | {item['content_type']} | RSS {item['score']} | 适配 {item['editorial_score']} | 风险：{';'.join(item['editorial_breakdown'].get('caution_flags', [])[:2]) or '无'}"
        for item in content_pool.get("selected_for_reader", [])[:10]
    )
    source_evidence = source_evidence_blocks(source_items)
    if content_kind == "knowledge_share":
        article_label = "中文知识分享文章"
        scope_notes = """审稿重点：
1. 标题是否夸张，是否把资料中的能力、公告、工程实践写成过度结论。
2. 是否有事实边界问题：把单一来源观点写成行业共识，把营销说法写成事实，把资料没有说明的能力写进正文。
3. 是否有相对日期（今天/明天/下周一等），需要改成绝对日期。
4. 是否有无来源推测、推测 URL、虚构数据。
5. 是否适合用插件同步到知乎、稀土掘金、B站、CSDN、抖音、小红书等平台。
6. 硬规则：凡是标题、开头、意义或实践建议中出现日期、年份、百分比、百分点、模型名、数据集名、benchmark/评测数字、工具数量、场景数量、成本/延迟等具体数字，必须逐项对照“来源证据摘录”核对。不能在来源证据中找到明确支持时，必须标为 high，并要求删除或改成“来源未明确给出”的谨慎表述。
7. 硬规则：如果文章中的数字与来源证据不一致，必须标为 high，并在 suggestion 中给出来源证据里的正确数字。
8. 硬规则：如果文章把“声称/据称/if true/claimed/alleged/未经证实/未确认”的安全、入侵、攻破、泄露类信息当作已确认事实或主要卖点，必须标为 high，并要求改成可验证主题。"""
    else:
        article_label = "中文技术情报日报"
        scope_notes = """审稿重点：
1. 标题是否夸张，是否把公告/工程实践写成事故。
2. 是否有事实边界问题：把“维护性通知”写成“攻击爆发”，把“防御架构公开”写成“安全事故”等。
3. 是否有相对日期（今天/明天/下周一等），需要改成绝对日期。
4. 是否有无来源推测、推测 URL、虚构数据。
5. 是否适合用插件同步到知乎、稀土掘金、B站、CSDN、抖音、小红书等平台。
6. 硬规则：凡是标题、开头、今日主线、意义或行动建议中出现日期、年份、百分比、百分点、模型名、数据集名、benchmark/评测数字、工具数量、场景数量、成本/延迟等具体数字，必须逐项对照“来源证据摘录”核对。不能在来源证据中找到明确支持时，必须标为 high，并要求删除或改成“来源未明确给出”的谨慎表述。
7. 硬规则：如果文章中的数字与来源证据不一致，必须标为 high，并在 suggestion 中给出来源证据里的正确数字。
8. 硬规则：如果标题或主线把“声称/据称/if true/claimed/alleged/未经证实/未确认”的安全、入侵、攻破、泄露类信息当作已确认事实或主要卖点，必须标为 high，并要求把标题改成可验证主题。"""
    return f"""请以发布前主编审稿人的身份，审查下面这篇{article_label}。

只输出 JSON，不要输出 Markdown。

{scope_notes}

评分标准：
- quality_score: 0-100，80 以上才适合直接发布。
- needs_revision: 只要有高风险事实边界、标题夸张、相对日期、内部编辑说明，或任何未核实/不一致的数字，就为 true。

返回 JSON 格式：
{{
  "quality_score": 0,
  "needs_revision": true,
  "summary": "一句话总评",
  "findings": [
    {{"severity": "high|medium|low", "issue": "问题", "suggestion": "修改建议"}}
  ],
  "safe_to_sync": false
}}

候选素材与类型：
{selected_summary}

来源证据摘录：
{source_evidence}

待审文章：
{article}
"""


def normalize_review(raw: str, heuristic_findings: list[dict]) -> dict:
    try:
        review = extract_json_object(raw)
    except Exception:
        review = {
            "quality_score": 70,
            "needs_revision": bool(heuristic_findings),
            "summary": "审稿 JSON 解析失败，仅保留规则检查结果。",
            "findings": [],
            "safe_to_sync": False,
        }
    findings = review.get("findings", [])
    if not isinstance(findings, list):
        findings = []
    findings.extend(heuristic_findings)
    high_or_medium = any(str(item.get("severity", "")).lower() in ("high", "medium") for item in findings)
    quality_score = int(review.get("quality_score", 70) or 70)
    review["quality_score"] = max(0, min(100, quality_score))
    review["findings"] = findings
    review["needs_revision"] = bool(review.get("needs_revision", False) or high_or_medium or review["quality_score"] < 80)
    review["safe_to_sync"] = bool(review.get("safe_to_sync", False) and not review["needs_revision"])
    review.setdefault("summary", "")
    return review


def build_article_rewrite_prompt(
    article: str,
    review: dict,
    source_items: list[FeedItem],
    content_kind: str = "daily_digest",
) -> str:
    findings = "\n".join(
        f"- [{item.get('severity', 'medium')}] {item.get('issue', '')} -> {item.get('suggestion', '')}"
        for item in review.get("findings", [])
    )
    source_evidence = source_evidence_blocks(source_items)
    article_label = "中文知识分享文章" if content_kind == "knowledge_share" else "中文技术情报日报"
    return f"""请根据审稿意见，改写下面这篇{article_label}。

要求：
- 保留原有事实和来源，不新增来源，不编造数据。
- 所有日期、百分比、百分点、模型名、benchmark 数字、工具数量、场景数量必须能被下面的“来源证据摘录”支持；不能支持就删除或改成不含具体数字的谨慎表述。
- 降低夸张标题和事故感，把事实边界写准确。
- 如果原标题围绕未经确认的安全/入侵类声称，必须把标题和主线改为可验证主题，例如预部署验证、权限边界、风险治理、工程验证流程；未经确认的声称只能作为正文中的谨慎引子。
- 相对日期改成绝对日期。
- 删除任何内部编辑说明。
- 输出 Markdown 正文，必须从一级标题 `# 标题` 开始。
- 保留“来源链接”章节。

审稿意见：
{findings}

来源证据摘录：
{source_evidence}

原文：
{article}
"""


def review_and_improve_article(
    article: str,
    env: dict,
    content_pool: dict,
    source_items: list[FeedItem],
    content_kind: str = "daily_digest",
    rewrite_system_prompt: str | None = None,
) -> tuple[str, dict]:
    heuristic_findings = deterministic_article_checks(article)
    log("Reviewing article quality with DeepSeek...")
    try:
        raw_review = deepseek_chat(
            env,
            build_article_review_prompt(article, content_pool, source_items, content_kind),
            timeout=180,
            system_prompt="你是严格的中文技术内容主编。你只输出 JSON，不输出 Markdown。",
        )
    except Exception as exc:
        log(f"WARN article review failed: {exc}")
        raw_review = json.dumps({
            "quality_score": 70,
            "needs_revision": bool(heuristic_findings),
            "summary": "模型审稿失败，仅保留规则检查结果。",
            "findings": [],
            "safe_to_sync": not heuristic_findings,
        }, ensure_ascii=False)
    review = normalize_review(raw_review, heuristic_findings)
    if not review["needs_revision"]:
        return article, review

    log("Article review requested revision; rewriting once...")
    try:
        revised = sanitize_article(deepseek_chat(
            env,
            build_article_rewrite_prompt(article, review, source_items, content_kind),
            timeout=180,
            system_prompt=rewrite_system_prompt or PROMPT_PATH.read_text(encoding="utf-8"),
        ))
    except Exception as exc:
        log(f"WARN article rewrite failed: {exc}")
        review["revision_applied"] = False
        review["safe_to_sync"] = False
        review["summary"] = (review.get("summary", "") + " 自动改写失败，需要人工处理。").strip()
        return article, review
    second_findings = deterministic_article_checks(revised)
    review["revision_applied"] = True
    review["post_revision_findings"] = second_findings
    if second_findings:
        review["safe_to_sync"] = False
        review["needs_revision"] = True
        review["quality_score"] = min(int(review.get("quality_score", 70)), 79)
    else:
        review["safe_to_sync"] = True
        review["needs_revision"] = False
        review["quality_score"] = max(int(review.get("quality_score", 80)), 80)
    return revised, review


def article_review_to_markdown(review: dict) -> str:
    lines = [
        "# 发布前审稿",
        "",
        f"- 质量分：{review.get('quality_score')}",
        f"- 是否需要修改：{review.get('needs_revision')}",
        f"- 是否建议同步：{review.get('safe_to_sync')}",
        f"- 总评：{review.get('summary', '')}",
        f"- 已自动改写：{review.get('revision_applied', False)}",
        "",
        "## 问题清单",
        "",
    ]
    findings = review.get("findings", [])
    if not findings:
        lines.append("- 未发现明显问题。")
    for item in findings:
        lines.append(f"- [{item.get('severity', 'medium')}] {item.get('issue', '')} -> {item.get('suggestion', '')}")
    post = review.get("post_revision_findings", [])
    if post:
        lines.extend(["", "## 自动改写后仍需人工注意", ""])
        for item in post:
            lines.append(f"- [{item.get('severity', 'medium')}] {item.get('issue', '')} -> {item.get('suggestion', '')}")
    lines.append("")
    return "\n".join(lines)


def write_article_review(review: dict, timestamp: str, run_dir: Path) -> tuple[Path, Path, Path]:
    json_path = run_dir / f"article-review-{timestamp}.json"
    md_path = run_dir / f"article-review-{timestamp}.md"
    latest_json = OUT_DIR / "article-review-latest.json"
    latest_md = OUT_DIR / "article-review-latest.md"
    write_review_record(
        review,
        latest_json=latest_json,
        latest_md=latest_md,
        run_id=timestamp,
        dated_json=json_path,
        dated_md=md_path,
    )
    return json_path, md_path, latest_md


def build_no_publish_article(topic_candidates: dict) -> str:
    gate = topic_candidates.get("gate", {})
    lines = [
        "# 今日无强主线，建议暂不发布主文",
        "",
        "今天的内容池没有通过发布闸门的 A/B 级选题。系统建议不要为了完成日报而硬写一篇主文。",
        "",
        "## 为什么不建议发布",
        "",
        f"- 闸门结论：{gate.get('decision', 'REJECT')}",
        f"- 原因：{gate.get('reason', '')}",
        "",
        "## 可人工参考的候选",
        "",
    ]
    for candidate in topic_candidates.get("candidates", []):
        lines.extend([
            f"### [{candidate.get('grade')}] {candidate.get('topic')}",
            "",
            f"- 建议动作：{candidate.get('recommended_action')}",
            f"- 候选标题：{candidate.get('working_title')}",
            f"- 为什么值得写：{candidate.get('why_worth_writing')}",
            f"- 为什么可能不值得写：{candidate.get('why_not')}",
            "",
        ])
    lines.extend([
        "## 下一步建议",
        "",
        "- 人工从内容池中选择一个更强主线后手动重跑。",
        "- 或者只发短观察，不生成跨平台长文。",
        "- 如果连续多天无强主线，优先扩充高质量一手来源，而不是放宽发布标准。",
        "",
    ])
    return "\n".join(lines)


def build_rejected_review(topic_candidates: dict) -> dict:
    gate = topic_candidates.get("gate", {})
    return {
        "quality_score": 0,
        "needs_revision": True,
        "summary": "选题闸门未通过：不建议发布主文。",
        "findings": [
            {
                "severity": "high",
                "issue": "今日无 A/B 级强选题",
                "suggestion": gate.get("reason", "不要强行成文，建议人工选题或只发短观察。"),
            }
        ],
        "safe_to_sync": False,
        "revision_applied": False,
        "gate_decision": gate,
    }


def build_blocked_platform_pack(topic_candidates: dict) -> dict:
    reason = topic_candidates.get("gate", {}).get("reason", "今日无强主线。")
    message = f"今日选题闸门未通过：{reason} 不建议同步发布。"
    return {
        "zhihu": {"title": "今日不建议发布主文", "topics": [], "summary": message},
        "juejin": {"category": "阅读", "tags": [], "summary": message},
        "csdn": {"title": "今日不建议发布主文", "tags": [], "summary": message, "category": "其他"},
        "douyin": {"title": "今日不建议发布", "summary": "选题闸门未通过", "hashtags": [], "cover_ratio": "3:4", "cover_size": "3:4"},
        "xiaohongshu": {"title": "今日不建议发布", "body": message, "hashtags": [], "cover_ratio": "3:4", "cover_size": "3:4"},
        "bilibili": {"title": "今日不建议发布主文", "summary": message, "topic": "人工智能", "cover_ratio": "16:9", "cover_size": "16:9"},
    }


def write_platform_pack_payload(pack: dict, timestamp: str, run_dir: Path) -> tuple[Path, Path, Path]:
    pack = normalize_platform_pack(pack)
    json_path = run_dir / f"platform-pack-{timestamp}.json"
    md_path = run_dir / f"platform-pack-{timestamp}.md"
    latest_json = OUT_DIR / "platform-pack-latest.json"
    latest_md = OUT_DIR / "platform-pack-latest.md"
    json_text = json.dumps(pack, ensure_ascii=False, indent=2)
    md_text = platform_pack_to_markdown(pack)
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    return json_path, md_path, latest_md


def write_cover_prompt(article: str, timestamp: str, run_dir: Path) -> Path:
    title, summary = extract_title_and_summary(article)
    template = COVER_PROMPT_PATH.read_text(encoding="utf-8")
    prompt = template.replace("{{article_title}}", title).replace("{{article_summary}}", summary)
    path = run_dir / f"cover-prompt-{timestamp}.txt"
    path.write_text(prompt, encoding="utf-8")
    return path


def limit_text(value: str, max_len: int) -> str:
    value = clean_field_text(value)
    if len(value) <= max_len:
        return value
    return value[: max_len - 1].rstrip("，。；、 ") + "…"


def clean_field_text(value: object) -> str:
    value = str(value or "")
    value = value.replace("\u00a0", " ").replace("\u3000", " ")
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def list_limit(values: object, count: int, item_max: int = 12) -> list[str]:
    if not isinstance(values, list):
        return []
    result = []
    for value in values:
        text = limit_text(str(value).lstrip("#"), item_max)
        if text and text not in result:
            result.append(text)
        if len(result) >= count:
            break
    return result


def extract_json_object(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def normalize_platform_pack(pack: dict) -> dict:
    allowed_platforms = ("zhihu", "juejin", "csdn", "douyin", "xiaohongshu", "bilibili")
    normalized = {
        key: dict(pack.get(key, {}) or {})
        for key in allowed_platforms
    }

    zhihu = normalized.setdefault("zhihu", {})
    zhihu["title"] = limit_text(zhihu.get("title", ""), 50)
    zhihu["topics"] = list_limit(zhihu.get("topics", []), 3)
    zhihu["summary"] = limit_text(zhihu.get("summary", ""), 120)
    zhihu["cover_ratio"] = "16:9"
    zhihu["ai_statement"] = "包含 AI 辅助创作"

    juejin = normalized.setdefault("juejin", {})
    juejin["category"] = "人工智能"
    juejin["tags"] = list_limit(juejin.get("tags", []), 3)
    juejin["summary"] = limit_text(juejin.get("summary", ""), 100)
    juejin["cover_ratio"] = "16:9"

    csdn = normalized.setdefault("csdn", {})
    csdn["title"] = limit_text(csdn.get("title", ""), 100)
    csdn["tags"] = list_limit(csdn.get("tags", []), 5)
    csdn["summary"] = limit_text(csdn.get("summary", ""), 256)
    csdn["category"] = limit_text(csdn.get("category", "网络安全"), 20)
    csdn["cover_ratio"] = "16:9"
    csdn["ai_statement"] = "部分由 AI 辅助生成"

    douyin = normalized.setdefault("douyin", {})
    douyin["title"] = limit_text(douyin.get("title", ""), 30)
    douyin["summary"] = limit_text(douyin.get("summary", ""), 30)
    douyin["hashtags"] = list_limit(douyin.get("hashtags", []), 5)
    douyin["cover_ratio"] = "3:4"
    douyin["cover_size"] = "3:4"

    xhs = normalized.setdefault("xiaohongshu", {})
    xhs["title"] = limit_text(xhs.get("title", ""), 20)
    xhs["body"] = limit_text(xhs.get("body", ""), 1000)
    xhs["hashtags"] = list_limit(xhs.get("hashtags", []), 5)
    xhs["cover_ratio"] = "3:4"
    xhs["cover_size"] = "3:4"

    bilibili = normalized.setdefault("bilibili", {})
    fallback_title = zhihu.get("title") or csdn.get("title") or douyin.get("title")
    bilibili["title"] = limit_text(bilibili.get("title", fallback_title), 80)
    fallback_summary = zhihu.get("summary") or csdn.get("summary") or douyin.get("summary")
    bilibili["summary"] = limit_text(bilibili.get("summary", fallback_summary), 250)
    topics = bilibili.get("topics", [])
    if not isinstance(topics, list):
        topics = [topics]
    topic = bilibili.get("topic") or (topics[0] if topics else "")
    if not topic:
        topic = (zhihu.get("topics") or ["人工智能"])[0]
    bilibili["topic"] = limit_text(str(topic).lstrip("#"), 20)
    bilibili["cover_ratio"] = "16:9"
    bilibili["cover_size"] = "16:9"
    bilibili["ai_statement"] = "AI 辅助创作声明"

    return normalized


def build_platform_prompt(article: str, platforms: dict) -> str:
    return f"""请根据下面的平台规则和文章，生成多平台发布字段包。

平台规则：
{json.dumps(platforms, ensure_ascii=False, indent=2)}

发布字段要求：
- 标题和摘要必须忠实于文章事实边界，不要为了平台点击率加重语气。
- 所有字段不得包含首尾空格；标题、摘要、标签、话题内部不要出现多余空格。
- 需要填写的话题/标签只输出纯文本，不要带 #，不要带多余标点。
- 如果正文说明两个来源并非直接回应、并非对立，平台标题禁止使用“vs”“对决”“开战”“博弈”“站队”等制造冲突的表达。
- 如果正文是短观察、单来源观察或轻量补位内容，平台字段也要体现“观察/信号/参考”，不要包装成重磅深度稿。
- 除非文章和来源明确支持，否则禁止使用：全面告警、永远不会修复、永无补丁、永不修复、官方承认、全网攻击、越狱、攻击爆发、重大事故。
- 如果文章表达为“可能、需要检查、记录更正、配置缓解”，平台字段也必须保持同样谨慎。
- 抖音标题和摘要都必须 30 字以内，封面比例固定 3:4。
- 小红书标题必须 20 字以内，正文适合笔记，不要额外生成导语字段。
- 稀土掘金 category 必须是“人工智能”。
- CSDN 摘要必须 256 字以内。
- B站只生成 1 个 topic；如果没有合适话题，优先用“人工智能”。

文章：
{article}
"""


def platform_pack_to_markdown(pack: dict) -> str:
    lines = ["# 平台发布字段包", ""]
    labels = {
        "zhihu": "知乎",
        "juejin": "稀土掘金",
        "csdn": "CSDN",
        "douyin": "抖音",
        "xiaohongshu": "小红书",
        "bilibili": "B站",
    }
    for key, label in labels.items():
        data = pack.get(key, {})
        lines.append(f"## {label}")
        for field, value in data.items():
            if isinstance(value, list):
                value = "、".join(value)
            lines.append(f"- {field}: {value}")
        lines.append("")
    return "\n".join(lines)


def write_platform_pack(article: str, env: dict, timestamp: str, run_dir: Path) -> tuple[Path, Path, Path]:
    platforms = json.loads(PLATFORMS_PATH.read_text(encoding="utf-8"))
    prompt = build_platform_prompt(article, platforms)
    log("Generating platform publishing pack with DeepSeek...")
    raw = deepseek_chat(
        env,
        prompt,
        timeout=180,
        system_prompt=PLATFORM_PROMPT_PATH.read_text(encoding="utf-8")
    )
    return write_platform_pack_payload(extract_json_object(raw), timestamp, run_dir)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--limit-per-feed", type=int, default=5)
    parser.add_argument("--feed-timeout", type=int, default=12)
    parser.add_argument("--reader-timeout", type=int, default=18)
    parser.add_argument("--pool-size", type=int, default=30)
    parser.add_argument("--retry-of", default=None, help="关联一次失败运行的 run_id，不改变正常输出流程")
    args = parser.parse_args()

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    env = load_env()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_date = time.strftime("%Y-%m-%d")
    run_dir = OUT_DIR / run_date
    run_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    global CURRENT_MANIFEST
    manifest = RunManifest(run_dir, "daily_digest", timestamp, retry_of=args.retry_of)
    CURRENT_MANIFEST = manifest

    items = manifest.run_stage("collect", lambda: collect_items(config, args.limit_per_feed, args.feed_timeout))
    history = manifest.run_stage("dedupe", lambda: load_recent_history(days=7))
    manifest.run_stage("score", lambda: apply_history_penalties(items, history))
    items = manifest.run_stage("select", lambda: sorted(items, key=final_rank_score, reverse=True))
    if history:
        log(
            "Loaded recent history: "
            f"{len(history.get('urls', []))} urls, "
            f"{len(history.get('titles', []))} pool titles, "
            f"{len(history.get('article_titles', []))} article titles"
        )
    selected = select_items_for_article(items, args.top)
    if not selected:
        raise RuntimeError("No feed items collected.")

    content_pool, content_pool_json_path, content_pool_md_path, content_pool_latest_path = manifest.run_stage(
        "content_pool", lambda: write_content_pool(items, selected, timestamp, run_dir, args.pool_size)
    )

    manifest.run_stage("reader", lambda: enrich_with_reader(selected, env, args.reader_timeout))
    fact_cards = manifest.run_stage("fact_cards", lambda: build_fact_cards(selected, timestamp))
    fact_cards_json_path, fact_cards_md_path, fact_cards_latest_path = manifest.run_stage(
        "fact_cards_output", lambda: write_fact_cards(fact_cards, timestamp, run_dir)
    )
    topic_candidates, topic_json_path, topic_md_path, topic_latest_path = manifest.run_stage(
        "topic_candidates", lambda: generate_topic_candidates(env, fact_cards, config["profile"], timestamp, run_dir)
    )

    gate = topic_candidates.get("gate", {})
    front = (
        "<!--\n"
        "Generated by content-pipeline daily digest\n"
        f"GeneratedAt: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Sources: {len(selected)} selected from {len(items)} collected items\n"
        f"ContentPool: content-pool-{timestamp}.md\n"
        f"FactCards: fact-cards-{timestamp}.md\n"
        f"TopicCandidates: topic-candidates-{timestamp}.md\n"
        f"ArticleReview: article-review-{timestamp}.md\n"
        f"GateDecision: {gate.get('decision', '')}\n"
        f"GateMode: {gate.get('mode', '')}\n"
        "-->\n\n"
    )

    article_path = run_dir / f"daily-digest-{timestamp}.md"
    latest_path = OUT_DIR / "draft-latest.md"

    if gate.get("decision") == "REJECT":
        article = build_no_publish_article(topic_candidates)
        article_review = build_rejected_review(topic_candidates)
        article_path.write_text(front + article, encoding="utf-8")
        latest_path.write_text(front + article, encoding="utf-8")
        review_json_path, review_md_path, review_latest_path = write_article_review(article_review, timestamp, run_dir)
        cover_path = None
        platform_json_path, platform_md_path, platform_latest_path = write_platform_pack_payload(
            build_blocked_platform_pack(topic_candidates),
            timestamp,
            run_dir,
        )
        log("Topic gate rejected article generation.")
    else:
        prompt = build_article_prompt(selected, config["profile"], content_pool, fact_cards, topic_candidates)
        log("Generating daily digest with DeepSeek...")
        article = manifest.run_stage("article_generation", lambda: sanitize_article(deepseek_chat(env, prompt)))
        article, article_review = manifest.run_stage(
            "article_review", lambda: review_and_improve_article(article, env, content_pool, selected)
        )
        article_path.write_text(front + article, encoding="utf-8")
        latest_path.write_text(front + article, encoding="utf-8")
        review_json_path, review_md_path, review_latest_path = write_article_review(article_review, timestamp, run_dir)
        cover_path = write_cover_prompt(article, timestamp, run_dir)
        if not article_review.get("safe_to_sync"):
            log("Article review did not recommend sync; generating platform pack for manual review anyway.")
        platform_json_path, platform_md_path, platform_latest_path = manifest.run_stage(
            "platform_pack", lambda: write_platform_pack(article, env, timestamp, run_dir)
        )

    manifest.finish("succeeded")

    log("Daily digest saved:")
    log(str(article_path))
    log("Content pool saved:")
    log(str(content_pool_json_path))
    log(str(content_pool_md_path))
    log("Latest content pool saved:")
    log(str(content_pool_latest_path))
    log("Fact cards saved:")
    log(str(fact_cards_json_path))
    log(str(fact_cards_md_path))
    log("Latest fact cards saved:")
    log(str(fact_cards_latest_path))
    log("Topic candidates saved:")
    log(str(topic_json_path))
    log(str(topic_md_path))
    log("Latest topic candidates saved:")
    log(str(topic_latest_path))
    log("Latest draft saved:")
    log(str(latest_path))
    log("Article review saved:")
    log(str(review_json_path))
    log(str(review_md_path))
    log("Latest article review saved:")
    log(str(review_latest_path))
    if cover_path:
        log("Cover prompt saved:")
        log(str(cover_path))
    else:
        log("Cover prompt skipped because topic gate rejected publishing.")
    log("Platform pack saved:")
    log(str(platform_json_path))
    log(str(platform_md_path))
    log("Latest platform pack saved:")
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
