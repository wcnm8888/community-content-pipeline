"""为失败的本地内容生产运行生成或执行安全重试计划。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

try:
    from .run_manifest import load_manifest
except ImportError:
    from run_manifest import load_manifest


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"


def build_plan(manifest: dict, requested_stage: str) -> dict:
    failed = [name for name, stage in manifest.get("stages", {}).items() if stage.get("status") == "failed"]
    stage = requested_stage
    if stage == "auto":
        stage = "render" if failed and all(name.endswith("_output") or name in {"platform_pack", "cover_prompt"} for name in failed) else "all"
    if stage == "render":
        if manifest.get("pipeline") == "daily_digest":
            scripts = ["render_content_pool_html.py", "render_topic_candidates_html.py", "render_draft_html.py", "render_article_review_html.py", "render_platform_pack_html.py"]
        else:
            scripts = ["render_knowledge_share_html.py", "render_article_review_html.py", "render_platform_pack_html.py"]
        return {"mode": "render", "pipeline": manifest["pipeline"], "scripts": scripts, "retry_of": manifest["run_id"]}
    if manifest.get("pipeline") not in {"daily_digest", "knowledge_share"}:
        raise ValueError(f"Unsupported pipeline: {manifest.get('pipeline')}")
    return {"mode": "all", "pipeline": manifest["pipeline"], "retry_of": manifest["run_id"]}


def execute(plan: dict) -> int:
    if plan["mode"] == "render":
        for name in plan["scripts"]:
            subprocess.run([sys.executable, str(ROOT / "scripts" / name)], cwd=ROOT, check=True)
        return 0
    script = "daily_digest.py" if plan["pipeline"] == "daily_digest" else "knowledge_share.py"
    command = [sys.executable, str(ROOT / "scripts" / script), "--retry-of", plan["retry_of"]]
    subprocess.run(command, cwd=ROOT, check=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id", help="失败运行的 run_id")
    parser.add_argument("--stage", choices=["auto", "all", "render"], default="auto")
    parser.add_argument("--execute", action="store_true", help="执行计划；默认只打印计划")
    args = parser.parse_args()
    manifest = load_manifest(OUT_DIR, args.run_id)
    if manifest.get("status") != "failed":
        raise RuntimeError("Only failed runs can be retried")
    plan = build_plan(manifest, args.stage)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return execute(plan) if args.execute else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
