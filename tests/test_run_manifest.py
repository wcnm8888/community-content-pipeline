import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_manifest import RunManifest
from scripts.retry_run import build_plan


class RunManifestTests(unittest.TestCase):
    def test_failed_stage_is_persisted_without_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = RunManifest(Path(directory), "daily_digest", "20260727-120000")
            manifest.start_stage("reader")
            manifest.fail_stage("reader", RuntimeError("token=secret-value upstream timeout"))
            payload = json.loads((Path(directory) / "run-manifest-20260727-120000.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["stages"]["reader"]["status"], "failed")
            self.assertNotIn("secret-value", json.dumps(payload))

    def test_render_retry_plan_does_not_publish(self):
        plan = build_plan({
            "run_id": "r1",
            "pipeline": "daily_digest",
            "status": "failed",
            "stages": {"article_review_output": {"status": "failed"}},
        }, "auto")
        self.assertEqual(plan["mode"], "render")
        self.assertNotIn("publish", " ".join(plan["scripts"]))


if __name__ == "__main__":
    unittest.main()
