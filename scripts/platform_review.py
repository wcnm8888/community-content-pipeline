"""Persist per-platform review and manual publishing preparation state."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


PLATFORMS = ("zhihu", "juejin", "csdn", "douyin", "xiaohongshu", "bilibili")
ALLOWED_STATUSES = {"pending", "approved", "revision_requested", "rejected", "draft_saved", "publish_confirmed"}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _markdown(record: dict[str, Any]) -> str:
    lines = [f"# 平台版本审核", "", f"- 文章运行 ID：{record.get('article_run_id', '')}", "", "## 平台状态", ""]
    for key, item in record.get("platforms", {}).items():
        lines.append(f"- {key}: {item.get('status', 'pending')} - {item.get('note', '')}")
    return "\n".join(lines) + "\n"


def write_platform_review(out_dir: Path, article_run_id: str, run_id: str, dated_dir: Path | None = None) -> dict[str, Any]:
    record = {
        "run_id": run_id,
        "article_run_id": article_run_id,
        "generated_at": _now(),
        "overall_status": "pending",
        "platforms": {key: {"status": "pending", "note": "", "reviewed_at": None, "reviewer": None} for key in PLATFORMS},
        "history": [],
    }
    _write_review_files(out_dir, record, dated_dir)
    return record


def _write_review_files(out_dir: Path, record: dict[str, Any], dated_dir: Path | None = None) -> None:
    latest_json = out_dir / "platform-review-latest.json"
    latest_md = out_dir / "platform-review-latest.md"
    _atomic_json(latest_json, record)
    latest_md.write_text(_markdown(record), encoding="utf-8")
    if dated_dir is not None:
        dated_json = dated_dir / f"platform-review-{record['run_id']}.json"
        dated_md = dated_dir / f"platform-review-{record['run_id']}.md"
        _atomic_json(dated_json, record)
        dated_md.write_text(_markdown(record), encoding="utf-8")


def update_platform_review(out_dir: Path, platform: str, status: str, note: str = "", run_id: str = "") -> dict[str, Any]:
    if platform not in PLATFORMS:
        raise ValueError(f"Unsupported platform: {platform}")
    if status not in ALLOWED_STATUSES - {"pending"}:
        raise ValueError(f"Unsupported platform review status: {status}")
    latest_json = out_dir / "platform-review-latest.json"
    if not latest_json.exists():
        raise FileNotFoundError(f"Platform review file not found: {latest_json}")
    record = json.loads(latest_json.read_text(encoding="utf-8"))
    if run_id and str(record.get("run_id", "")) != run_id:
        raise ValueError("Platform review run_id does not match the latest record")
    item = record["platforms"].setdefault(platform, {"status": "pending"})
    old_status = item.get("status", "pending")
    now = _now()
    item.update({"status": status, "note": str(note).strip()[:2000], "reviewed_at": now, "reviewer": "local_user"})
    record["history"].append({"platform": platform, "from": old_status, "to": status, "note": str(note).strip()[:2000], "reviewed_at": now})
    statuses = [record["platforms"].get(key, {}).get("status", "pending") for key in PLATFORMS]
    record["overall_status"] = "approved" if all(value == "approved" for value in statuses) else "in_review"
    dated_dir = next(iter(out_dir.glob(f"*/platform-review-{record['run_id']}.json")), None)
    _write_review_files(out_dir, record, dated_dir.parent if dated_dir else None)
    return record
