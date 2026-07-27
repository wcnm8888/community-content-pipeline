import json
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    from .review_state import update_review_files
    from .platform_review import update_platform_review as persist_platform_review
except ImportError:
    from review_state import update_review_files
    from platform_review import update_platform_review as persist_platform_review


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
DRYRUN_PLATFORMS = {"zhihu", "juejin", "csdn", "douyin", "xiaohongshu", "bilibili"}
DAILY_RUN_LOCK = threading.Lock()


def run_command(args: list[str], timeout: int = 900) -> tuple[int, str]:
    proc = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout


def safe_output(value: str, limit: int = 12000) -> str:
    text = str(value or "")
    for key in ("cookie", "token", "password", "passwd", "secret", "authorization", "api_key", "private_key"):
        text = re.sub(rf"(?i)({key})\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", text)
    return text[-limit:]


def load_latest_manifest() -> tuple[str, dict | None]:
    latest = ROOT / "out" / "run-manifest-latest.json"
    if not latest.exists():
        return "", None
    try:
        payload = json.loads(latest.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return "", None
    run_id = str(payload.get("run_id", ""))
    dated = ROOT / "out" / time.strftime("%Y-%m-%d") / f"run-manifest-{run_id}.json"
    return str(dated if dated.exists() else latest), payload


def build_daily_response(request_id: str, stage_codes: dict[str, int], outputs: dict[str, str]) -> dict:
    manifest_path, manifest = load_latest_manifest()
    failed_stage = None
    for stage, code in stage_codes.items():
        if code != 0:
            failed_stage = stage
            break
    ok = failed_stage is None
    if manifest and manifest.get("status") == "failed" and not failed_stage:
        failed_stage = next(
            (name for name, item in manifest.get("stages", {}).items() if item.get("status") == "failed"),
            "daily_digest",
        )
        ok = False
    run_id = str(manifest.get("run_id", "")) if manifest else ""
    return {
        "ok": ok,
        "request_id": request_id,
        "run_id": run_id,
        "pipeline": "daily_digest",
        "status": "succeeded" if ok else "failed",
        "failed_stage": failed_stage,
        "retryable": not ok,
        "manifest": {
            "path": manifest_path,
            "status": manifest.get("status") if manifest else None,
            "failed_stage": failed_stage,
            "data": manifest,
        },
        "article_review_url": "http://localhost:8010/article-review-latest.html",
        "platform_pack_url": "http://localhost:8010/platform-pack-latest.html",
        "preview_url": "http://localhost:8010/draft-latest.html",
        "outputs": {key: safe_output(value, 4000) for key, value in outputs.items()},
    }


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "http://localhost:8010")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "http://localhost:8010")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json(200, {"ok": True})
            return
        self.send_json(404, {"ok": False, "error": "not found"})

    def read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        if not raw.strip():
            return {}
        return json.loads(raw)

    def do_POST(self) -> None:
        if self.path == "/review":
            self.update_review()
            return
        if self.path == "/platform-review":
            self.update_platform_review()
            return
        if self.path == "/run-knowledge":
            self.run_knowledge()
            return
        if self.path == "/dryrun":
            self.run_dryrun()
            return

        if self.path != "/run-daily":
            self.send_json(404, {"ok": False, "error": "not found"})
            return

        body = self.read_json_body()
        request_id = str(body.get("request_id", "")).strip() or uuid.uuid4().hex
        if not DAILY_RUN_LOCK.acquire(blocking=False):
            self.send_json(
                409,
                {
                    "ok": False,
                    "request_id": request_id,
                    "pipeline": "daily_digest",
                    "status": "already_running",
                    "retryable": True,
                    "error": "another daily digest is already running",
                },
            )
            return

        try:
            stage_codes: dict[str, int] = {}
            outputs: dict[str, str] = {}
            stage_codes["daily_digest"], outputs["daily_digest"] = run_command(
                [
                    PYTHON,
                    "scripts/daily_digest.py",
                    "--top", "8", "--limit-per-feed", "5", "--feed-timeout", "12",
                    "--reader-timeout", "18", "--pool-size", "30",
                ],
                timeout=1200,
            )
            stage_codes["content_pool_render"], outputs["content_pool_render"] = run_command([PYTHON, "scripts/render_content_pool_html.py"], timeout=60)
            stage_codes["topic_candidates_render"], outputs["topic_candidates_render"] = run_command([PYTHON, "scripts/render_topic_candidates_html.py"], timeout=60)
            stage_codes["draft_render"], outputs["draft_render"] = run_command([PYTHON, "scripts/render_draft_html.py"], timeout=60)
            stage_codes["article_review_render"], outputs["article_review_render"] = run_command([PYTHON, "scripts/render_article_review_html.py"], timeout=60)
            stage_codes["platform_pack_render"], outputs["platform_pack_render"] = run_command([PYTHON, "scripts/render_platform_pack_html.py"], timeout=60)
            result = build_daily_response(request_id, stage_codes, outputs)
            self.send_json(200 if result["ok"] else 500, result)
        except subprocess.TimeoutExpired as exc:
            self.send_json(
                504,
                {
                    "ok": False,
                    "request_id": request_id,
                    "pipeline": "daily_digest",
                    "status": "failed",
                    "failed_stage": "daily_digest",
                    "retryable": True,
                    "error": "daily digest timed out",
                    "output": safe_output(exc.stdout or "", 8000) if isinstance(exc.stdout, str) else "",
                },
            )
        except Exception as exc:
            self.send_json(500, {"ok": False, "request_id": request_id, "pipeline": "daily_digest", "status": "failed", "retryable": True, "error": safe_output(str(exc), 1000)})
        finally:
            DAILY_RUN_LOCK.release()

    def update_review(self) -> None:
        try:
            body = self.read_json_body()
            status = str(body.get("status", "")).strip()
            note = str(body.get("note", ""))
            run_id = str(body.get("run_id", "")).strip()
            if not status:
                self.send_json(400, {"ok": False, "error": "status is required"})
                return
            review = update_review_files(ROOT / "out", status, note, run_id)
            platform_generation = None
            if status == "approved":
                generation_code, generation_out = run_command(
                    [PYTHON, "scripts/generate_platform_versions.py", "--run-id", str(review.get("run_id", ""))],
                    timeout=1200,
                )
                platform_generation = {"exit_code": generation_code, "output": generation_out[-6000:]}
                if generation_code != 0:
                    self.send_json(500, {"ok": False, "review_saved": True, "error": "article approved but platform generation failed", "platform_generation": platform_generation})
                    return
            render_code, render_out = run_command(
                [PYTHON, "scripts/render_article_review_html.py"],
                timeout=60,
            )
            if status == "approved":
                render_code, render_out = run_command([PYTHON, "scripts/render_platform_pack_html.py"], timeout=60)
            if render_code != 0:
                self.send_json(500, {"ok": False, "error": "review saved but render failed", "output": render_out[-4000:]})
                return
            self.send_json(
                200,
                {
                    "ok": True,
                    "run_id": review.get("run_id", ""),
                    "review_status": review.get("review_status", ""),
                    "human_review": review.get("human_review", {}),
                    "platform_generation": platform_generation,
                },
            )
        except ValueError as exc:
            self.send_json(409, {"ok": False, "error": str(exc)})
        except FileNotFoundError as exc:
            self.send_json(404, {"ok": False, "error": str(exc)})
        except Exception as exc:
            self.send_json(500, {"ok": False, "error": str(exc)})

    def update_platform_review(self) -> None:
        try:
            body = self.read_json_body()
            record = persist_platform_review(
                ROOT / "out",
                str(body.get("platform", "")).strip(),
                str(body.get("status", "")).strip(),
                str(body.get("note", "")),
                str(body.get("run_id", "")).strip(),
            )
            render_code, render_out = run_command([PYTHON, "scripts/render_platform_pack_html.py"], timeout=60)
            if render_code != 0:
                self.send_json(500, {"ok": False, "error": "platform review saved but render failed", "output": render_out[-4000:]})
                return
            platform = str(body.get("platform", "")).strip()
            self.send_json(200, {"ok": True, "platform": platform, "platform_review": record["platforms"].get(platform, {}), "overall_status": record["overall_status"]})
        except ValueError as exc:
            self.send_json(409, {"ok": False, "error": str(exc)})
        except FileNotFoundError as exc:
            self.send_json(404, {"ok": False, "error": str(exc)})
        except Exception as exc:
            self.send_json(500, {"ok": False, "error": str(exc)})

    def run_dryrun(self) -> None:
        try:
            body = self.read_json_body()
            platform = str(body.get("platform", "")).strip().lower()
            if platform not in DRYRUN_PLATFORMS:
                self.send_json(400, {"ok": False, "error": "unsupported platform"})
                return

            code, output = run_command(
                [
                    POWERSHELL,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(ROOT / "scripts" / "publish_daily.ps1"),
                    "-Platforms",
                    platform,
                    "-Mode",
                    "DryRun",
                ],
                timeout=900,
            )
            record_path = ROOT / "out" / "dryrun-latest.json"
            record = json.loads(record_path.read_text(encoding="utf-8-sig")) if record_path.exists() else None
            self.send_json(
                200 if code == 0 else 500,
                {
                    "ok": code == 0,
                    "platform": platform,
                    "exit_code": code,
                    "dryrun": record,
                    "output": output[-8000:],
                },
            )
        except subprocess.TimeoutExpired as exc:
            self.send_json(504, {"ok": False, "error": "platform dryrun timed out", "output": (exc.stdout or "")[-8000:] if isinstance(exc.stdout, str) else ""})
        except Exception as exc:
            self.send_json(500, {"ok": False, "error": str(exc)})

    def run_knowledge(self) -> None:
        try:
            body = self.read_json_body()
            topic = str(body.get("topic", "")).strip()
            if not topic:
                self.send_json(400, {"ok": False, "error": "topic is required"})
                return

            args = [
                PYTHON,
                "scripts/knowledge_share.py",
                "--topic",
                topic,
                "--top-results",
                "8",
                "--reader-timeout",
                "18",
            ]
            angle = str(body.get("angle", "")).strip()
            audience = str(body.get("audience", "")).strip()
            urls = body.get("urls", [])
            if angle:
                args.extend(["--angle", angle])
            if audience:
                args.extend(["--audience", audience])
            if isinstance(urls, str):
                urls = [urls]
            if isinstance(urls, list) and urls:
                args.append("--urls")
                args.extend(str(url).strip() for url in urls if str(url).strip())

            knowledge_code, knowledge_out = run_command(args, timeout=1200)
            render_code, render_out = run_command([PYTHON, "scripts/render_knowledge_share_html.py"], timeout=60)
            review_render_code, review_render_out = run_command(
                [PYTHON, "scripts/render_article_review_html.py"],
                timeout=60,
            )
            platform_render_code, platform_render_out = run_command(
                [PYTHON, "scripts/render_platform_pack_html.py"],
                timeout=60,
            )
            ok = knowledge_code == 0 and render_code == 0 and review_render_code == 0 and platform_render_code == 0
            self.send_json(
                200 if ok else 500,
                {
                    "ok": ok,
                    "knowledge_exit_code": knowledge_code,
                    "render_exit_code": render_code,
                    "review_render_exit_code": review_render_code,
                    "platform_render_exit_code": platform_render_code,
                    "knowledge_output": knowledge_out[-12000:],
                    "render_output": render_out[-4000:],
                    "review_render_output": review_render_out[-4000:],
                    "platform_render_output": platform_render_out[-4000:],
                    "knowledge_share_url": "http://localhost:8010/knowledge-share-latest.html",
                    "preview_url": "http://localhost:8010/knowledge-share-latest.html",
                    "article_review_url": "http://localhost:8010/article-review-latest.html",
                    "platform_pack_url": "http://localhost:8010/platform-pack-latest.html",
                },
            )
        except subprocess.TimeoutExpired as exc:
            self.send_json(
                504,
                {
                    "ok": False,
                    "error": "knowledge share generation timed out",
                    "output": (exc.stdout or "")[-8000:] if isinstance(exc.stdout, str) else "",
                },
            )
        except Exception as exc:
            self.send_json(500, {"ok": False, "error": str(exc)})

    def log_message(self, format: str, *args) -> None:
        sys.stdout.write("%s - %s\n" % (self.address_string(), format % args))
        sys.stdout.flush()


def main() -> int:
    server = ThreadingHTTPServer(("0.0.0.0", 8020), Handler)
    print("content worker listening on http://0.0.0.0:8020", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
