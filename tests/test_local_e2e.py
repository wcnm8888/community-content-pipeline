import json
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.platform_review import PLATFORMS, write_platform_review
from scripts.review_state import update_review_files, write_review_record
from scripts import worker_server


class LocalEndToEndTests(unittest.TestCase):
    def test_run_daily_returns_manifest_context(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            out_dir = root / "out"
            dated_dir = out_dir / "2026-07-27"
            dated_dir.mkdir(parents=True)
            run_id = "20260727-190000"
            manifest = {
                "run_id": run_id,
                "pipeline": "daily_digest",
                "status": "succeeded",
                "stages": {"article_generation": {"status": "succeeded"}},
            }

            class FakeServer(worker_server.ThreadingHTTPServer):
                allow_reuse_address = True

            def fake_command(args, timeout=900):
                if any("daily_digest.py" in str(item) for item in args):
                    out_dir.mkdir(parents=True, exist_ok=True)
                    (out_dir / "run-manifest-latest.json").write_text(json.dumps(manifest), encoding="utf-8")
                    (dated_dir / f"run-manifest-{run_id}.json").write_text(json.dumps(manifest), encoding="utf-8")
                return 0, "synthetic command completed"

            with patch.object(worker_server, "ROOT", root), patch.object(worker_server, "PYTHON", "python"), patch.object(worker_server, "run_command", side_effect=fake_command):
                server = FakeServer(("127.0.0.1", 0), worker_server.Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    result = self._post(server.server_address[1], "/run-daily", {"request_id": "n8n-test-1"})
                    self.assertTrue(result["ok"])
                    self.assertEqual(result["request_id"], "n8n-test-1")
                    self.assertEqual(result["run_id"], run_id)
                    self.assertEqual(result["status"], "succeeded")
                    self.assertTrue(result["manifest"]["path"].endswith(f"run-manifest-{run_id}.json"))
                    self.assertIn("article_review_url", result)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)

    def test_review_to_platform_review_and_worker_endpoints(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            out_dir = root / "out"
            dated_dir = out_dir / "2026-07-27"
            run_id = "20260727-120000"
            write_review_record(
                {"run_id": run_id, "quality_score": 90, "safe_to_sync": True},
                out_dir / "article-review-latest.json",
                out_dir / "article-review-latest.md",
                run_id,
                dated_dir / f"article-review-{run_id}.json",
                dated_dir / f"article-review-{run_id}.md",
            )

            class FakeServer(worker_server.ThreadingHTTPServer):
                allow_reuse_address = True

            with patch.object(worker_server, "ROOT", root), patch.object(worker_server, "PYTHON", "python"):
                def fake_command(args, timeout=900):
                    if any("generate_platform_versions.py" in str(item) for item in args):
                        write_platform_review(out_dir, run_id, run_id, dated_dir)
                    return 0, "synthetic command completed"

                with patch.object(worker_server, "run_command", side_effect=fake_command):
                    server = FakeServer(("127.0.0.1", 0), worker_server.Handler)
                    thread = threading.Thread(target=server.serve_forever, daemon=True)
                    thread.start()
                    try:
                        port = server.server_address[1]
                        approved = self._post(port, "/review", {"run_id": run_id, "status": "approved", "note": "文章通过"})
                        self.assertTrue(approved["ok"])
                        self.assertEqual(approved["review_status"], "approved")
                        for platform in PLATFORMS:
                            result = self._post(port, "/platform-review", {"run_id": run_id, "platform": platform, "status": "approved"})
                            self.assertTrue(result["ok"])
                        final = json.loads((out_dir / "platform-review-latest.json").read_text(encoding="utf-8"))
                        self.assertEqual(final["overall_status"], "approved")
                    finally:
                        server.shutdown()
                        server.server_close()
                        thread.join(timeout=2)

    @staticmethod
    def _post(port, path, payload):
        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        connection.request("POST", path, body=body, headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        result = json.loads(response.read().decode("utf-8"))
        connection.close()
        if response.status >= 400:
            raise AssertionError(f"HTTP {response.status}: {result}")
        return result


if __name__ == "__main__":
    unittest.main()
