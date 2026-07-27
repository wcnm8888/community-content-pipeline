"""Generate platform versions only after article human approval."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from daily_digest import OUT_DIR, deepseek_chat, load_env, write_platform_pack
from platform_review import write_platform_review


ROOT = Path(__file__).resolve().parents[1]


def _article_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return re.sub(r"\A<!--.*?-->\s*", "", text, flags=re.S).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    review_path = OUT_DIR / "article-review-latest.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if str(review.get("run_id", "")) != args.run_id:
        raise RuntimeError("Article review run_id does not match the requested platform generation")
    if review.get("review_status") != "approved":
        raise RuntimeError("Article must be human-approved before platform versions are generated")

    article_path = OUT_DIR / "draft-latest.md"
    if not article_path.exists():
        article_path = OUT_DIR / "knowledge-share-latest.md"
    if not article_path.exists():
        raise FileNotFoundError("No latest article draft found")
    dated_dir = next(iter(OUT_DIR.glob(f"*/article-review-{args.run_id}.json")), None)
    run_dir = dated_dir.parent if dated_dir else OUT_DIR / time.strftime("%Y-%m-%d")
    run_dir.mkdir(parents=True, exist_ok=True)
    env = load_env()
    result = write_platform_pack(_article_text(article_path), env, args.run_id, run_dir)
    record = write_platform_review(OUT_DIR, args.run_id, args.run_id, run_dir)
    print(json.dumps({"ok": True, "run_id": args.run_id, "platform_pack": str(result[0]), "platform_review": record}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
