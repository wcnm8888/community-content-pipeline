import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from review_state import update_review_files


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


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
        if self.path == "/run-knowledge":
            self.run_knowledge()
            return

        if self.path != "/run-daily":
            self.send_json(404, {"ok": False, "error": "not found"})
            return

        try:
            digest_code, digest_out = run_command(
                [
                    PYTHON,
                    "scripts/daily_digest.py",
                    "--top",
                    "8",
                    "--limit-per-feed",
                    "5",
                    "--feed-timeout",
                    "12",
                    "--reader-timeout",
                    "18",
                    "--pool-size",
                    "30",
                ],
                timeout=1200,
            )
            content_pool_render_code, content_pool_render_out = run_command(
                [PYTHON, "scripts/render_content_pool_html.py"],
                timeout=60,
            )
            topic_render_code, topic_render_out = run_command(
                [PYTHON, "scripts/render_topic_candidates_html.py"],
                timeout=60,
            )
            render_code, render_out = run_command([PYTHON, "scripts/render_draft_html.py"], timeout=60)
            review_render_code, review_render_out = run_command(
                [PYTHON, "scripts/render_article_review_html.py"],
                timeout=60,
            )
            platform_render_code, platform_render_out = run_command(
                [PYTHON, "scripts/render_platform_pack_html.py"],
                timeout=60,
            )
            ok = (
                digest_code == 0
                and content_pool_render_code == 0
                and topic_render_code == 0
                and render_code == 0
                and review_render_code == 0
                and platform_render_code == 0
            )
            self.send_json(
                200 if ok else 500,
                {
                    "ok": ok,
                    "digest_exit_code": digest_code,
                    "content_pool_render_exit_code": content_pool_render_code,
                    "topic_render_exit_code": topic_render_code,
                    "render_exit_code": render_code,
                    "review_render_exit_code": review_render_code,
                    "platform_render_exit_code": platform_render_code,
                    "digest_output": digest_out[-12000:],
                    "content_pool_render_output": content_pool_render_out[-4000:],
                    "topic_render_output": topic_render_out[-4000:],
                    "render_output": render_out[-4000:],
                    "review_render_output": review_render_out[-4000:],
                    "platform_render_output": platform_render_out[-4000:],
                    "content_pool_url": "http://localhost:8010/content-pool-latest.html",
                    "topic_candidates_url": "http://localhost:8010/topic-candidates-latest.html",
                    "preview_url": "http://localhost:8010/draft-latest.html",
                    "article_review_url": "http://localhost:8010/article-review-latest.html",
                    "platform_pack_url": "http://localhost:8010/platform-pack-latest.html",
                },
            )
        except subprocess.TimeoutExpired as exc:
            self.send_json(
                504,
                {
                    "ok": False,
                    "error": "daily digest timed out",
                    "output": (exc.stdout or "")[-8000:] if isinstance(exc.stdout, str) else "",
                },
            )
        except Exception as exc:
            self.send_json(500, {"ok": False, "error": str(exc)})

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
            render_code, render_out = run_command(
                [PYTHON, "scripts/render_article_review_html.py"],
                timeout=60,
            )
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
                },
            )
        except ValueError as exc:
            self.send_json(409, {"ok": False, "error": str(exc)})
        except FileNotFoundError as exc:
            self.send_json(404, {"ok": False, "error": str(exc)})
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
