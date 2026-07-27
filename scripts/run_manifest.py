"""结构化记录一次内容生产运行及各阶段结果。"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable, TypeVar


T = TypeVar("T")
SENSITIVE = re.compile(r"(?i)(cookie|token|password|passwd|secret|authorization|bearer|private.?key)\s*[:=]\s*[^\s,;]+")


def _safe_error(exc: BaseException) -> str:
    message = SENSITIVE.sub(r"\1=[REDACTED]", str(exc))
    return message[:1000]


class RunManifest:
    def __init__(self, out_dir: Path, pipeline: str, run_id: str, retry_of: str | None = None):
        self.path = out_dir / f"run-manifest-{run_id}.json"
        self.latest_path = out_dir / "run-manifest-latest.json"
        self.data: dict[str, Any] = {
            "run_id": run_id,
            "pipeline": pipeline,
            "status": "running",
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "finished_at": None,
            "retry_of": retry_of,
            "stages": {},
        }
        self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.data, ensure_ascii=False, indent=2)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(payload, encoding="utf-8")
        temp.replace(self.path)
        self.latest_path.write_text(payload, encoding="utf-8")

    def start_stage(self, name: str, attempt: int = 1) -> None:
        self.data["stages"][name] = {
            "status": "running",
            "attempt": attempt,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "finished_at": None,
            "error": None,
        }
        self._save()

    def succeed_stage(self, name: str) -> None:
        stage = self.data["stages"].setdefault(name, {})
        stage.update({"status": "succeeded", "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "error": None})
        self._save()

    def fail_stage(self, name: str, exc: BaseException) -> None:
        stage = self.data["stages"].setdefault(name, {})
        stage.update({"status": "failed", "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "error": _safe_error(exc)})
        self.data["status"] = "failed"
        self.data["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        self._save()

    def skip_stage(self, name: str, reason: str) -> None:
        self.data["stages"][name] = {
            "status": "skipped",
            "attempt": 1,
            "started_at": None,
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "error": _safe_error(RuntimeError(reason)),
        }
        if self.data.get("status") == "failed" and not any(
            stage.get("status") == "failed" for stage_name, stage in self.data["stages"].items() if stage_name != name
        ):
            self.data["status"] = "running"
            self.data["finished_at"] = None
        self._save()

    def finish(self, status: str = "succeeded") -> None:
        self.data["status"] = status
        self.data["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        self._save()

    def fail_run(self, exc: BaseException) -> None:
        self.data["status"] = "failed"
        self.data["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        self.data["unhandled_error"] = _safe_error(exc)
        self._save()

    def run_stage(self, name: str, action: Callable[[], T]) -> T:
        self.start_stage(name)
        try:
            result = action()
        except Exception as exc:
            self.fail_stage(name, exc)
            raise
        self.succeed_stage(name)
        return result


def load_manifest(out_dir: Path, run_id: str) -> dict[str, Any]:
    path = out_dir / f"run-manifest-{run_id}.json"
    if not path.exists():
        matches = list(out_dir.glob(f"*/run-manifest-{run_id}.json"))
        if matches:
            path = matches[0]
    if not path.exists():
        raise FileNotFoundError(f"Run manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))
