"""Persist the human review state for the latest generated article."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


ALLOWED_STATUSES = {
    "pending",
    "approved",
    "revision_requested",
    "rejected",
}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
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


def _review_markdown(review: dict[str, Any]) -> str:
    human = review.get("human_review") or {}
    findings = review.get("findings") or []
    post_findings = review.get("post_revision_findings") or []
    lines = [
        "# 发布前审稿",
        "",
        f"- 运行 ID：{review.get('run_id', '')}",
        f"- AI 质量分：{review.get('quality_score', '')}",
        f"- AI 是否需要修改：{'是' if review.get('needs_revision') else '否'}",
        f"- 人工审核状态：{human.get('status', 'pending')}",
        f"- 人工审核时间：{human.get('reviewed_at') or '未审核'}",
        "",
        "## AI 总评",
        "",
        str(review.get("summary", "")),
        "",
        "## 人工审核意见",
        "",
        str(human.get("note", "")),
        "",
        "## AI 问题清单",
        "",
    ]
    for item in findings:
        lines.append(
            f"- [{item.get('severity', 'medium')}] {item.get('issue', '')}：{item.get('suggestion', '')}"
        )
    if not findings:
        lines.append("- 未发现明显问题。")
    if post_findings:
        lines.extend(["", "## 自动改写后仍需人工注意", ""])
        for item in post_findings:
            lines.append(
                f"- [{item.get('severity', 'medium')}] {item.get('issue', '')}：{item.get('suggestion', '')}"
            )
    return "\n".join(lines) + "\n"


def normalize_review_record(review: dict[str, Any], run_id: str) -> dict[str, Any]:
    record = dict(review)
    record["run_id"] = str(record.get("run_id") or run_id)
    human = record.get("human_review")
    if not isinstance(human, dict):
        human = {}
    status = str(human.get("status") or record.get("review_status") or "pending")
    if status not in ALLOWED_STATUSES:
        status = "pending"
    record["review_status"] = status
    record["human_review"] = {
        "status": status,
        "note": str(human.get("note") or ""),
        "reviewed_at": human.get("reviewed_at"),
        "reviewer": str(human.get("reviewer") or "local_user"),
    }
    return record


def write_review_record(
    review: dict[str, Any],
    latest_json: Path,
    latest_md: Path,
    run_id: str,
    dated_json: Path | None = None,
    dated_md: Path | None = None,
) -> dict[str, Any]:
    record = normalize_review_record(review, run_id)
    _atomic_write_json(latest_json, record)
    latest_md.parent.mkdir(parents=True, exist_ok=True)
    latest_md.write_text(_review_markdown(record), encoding="utf-8")
    if dated_json is not None:
        _atomic_write_json(dated_json, record)
    if dated_md is not None:
        dated_md.parent.mkdir(parents=True, exist_ok=True)
        dated_md.write_text(_review_markdown(record), encoding="utf-8")
    return record


def update_human_review(
    review_path: Path,
    status: str,
    note: str = "",
    reviewer: str = "local_user",
) -> dict[str, Any]:
    if status not in ALLOWED_STATUSES - {"pending"}:
        raise ValueError(f"Unsupported human review status: {status}")
    if not review_path.exists():
        raise FileNotFoundError(f"Review file not found: {review_path}")
    review = json.loads(review_path.read_text(encoding="utf-8"))
    current = review.get("human_review") or {}
    review["human_review"] = {
        "status": status,
        "note": str(note).strip()[:2000],
        "reviewed_at": _now(),
        "reviewer": str(reviewer or "local_user")[:100],
    }
    review["review_status"] = status
    review["review_history"] = list(review.get("review_history") or [])
    review["review_history"].append({
        "from": current.get("status", "pending"),
        "to": status,
        "note": str(note).strip()[:2000],
        "reviewed_at": review["human_review"]["reviewed_at"],
        "reviewer": review["human_review"]["reviewer"],
    })
    _atomic_write_json(review_path, review)
    return review


def update_review_files(
    out_dir: Path,
    status: str,
    note: str = "",
    run_id: str = "",
) -> dict[str, Any]:
    latest_json = out_dir / "article-review-latest.json"
    latest_md = out_dir / "article-review-latest.md"
    review = json.loads(latest_json.read_text(encoding="utf-8"))
    if run_id and str(review.get("run_id", "")) != str(run_id):
        raise ValueError("Review run_id does not match the latest review")
    review = update_human_review(latest_json, status, note)
    latest_md.write_text(_review_markdown(review), encoding="utf-8")
    actual_run_id = str(review.get("run_id", ""))
    if actual_run_id:
        for dated_json in out_dir.glob(f"*/article-review-{actual_run_id}.json"):
            _atomic_write_json(dated_json, review)
            dated_md = dated_json.with_suffix(".md")
            dated_md.write_text(_review_markdown(review), encoding="utf-8")
    return review
