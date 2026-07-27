import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import worker_server


class WorkerRunResponseTests(unittest.TestCase):
    def test_daily_response_maps_manifest_and_render_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_dir = root / "out" / "2026-07-27"
            manifest_dir.mkdir(parents=True)
            manifest = {
                "run_id": "20260727-190000",
                "pipeline": "daily_digest",
                "status": "succeeded",
                "stages": {"article_generation": {"status": "succeeded"}},
            }
            (root / "out" / "run-manifest-latest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (manifest_dir / "run-manifest-20260727-190000.json").write_text(json.dumps(manifest), encoding="utf-8")
            with patch.object(worker_server, "ROOT", root):
                result = worker_server.build_daily_response(
                    "n8n-execution-1",
                    {"daily_digest": 0, "article_review_render": 0},
                    {"daily_digest": "done"},
                )
            self.assertTrue(result["ok"])
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["run_id"], "20260727-190000")
            self.assertTrue(result["manifest"]["path"].endswith("run-manifest-20260727-190000.json"))

    def test_daily_response_marks_render_failure_retryable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            latest = root / "out" / "run-manifest-latest.json"
            latest.parent.mkdir(parents=True)
            latest.write_text(json.dumps({"run_id": "run-2", "status": "succeeded", "stages": {}}), encoding="utf-8")
            with patch.object(worker_server, "ROOT", root):
                result = worker_server.build_daily_response(
                    "n8n-execution-2",
                    {"daily_digest": 0, "platform_pack_render": 1},
                    {"platform_pack_render": "safe output"},
                )
            self.assertFalse(result["ok"])
            self.assertEqual(result["failed_stage"], "platform_pack_render")
            self.assertTrue(result["retryable"])


if __name__ == "__main__":
    unittest.main()
