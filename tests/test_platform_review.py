import json
import tempfile
import unittest
from pathlib import Path

from scripts.platform_review import update_platform_review, write_platform_review


class PlatformReviewTests(unittest.TestCase):
    def test_platform_review_requires_all_platforms_for_overall_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            out_dir = Path(directory)
            write_platform_review(out_dir, "article-1", "platform-1")
            update_platform_review(out_dir, "zhihu", "approved", "通过", "platform-1")
            payload = json.loads((out_dir / "platform-review-latest.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["platforms"]["zhihu"]["status"], "approved")
            self.assertNotEqual(payload["overall_status"], "approved")

    def test_platform_review_run_id_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            out_dir = Path(directory)
            write_platform_review(out_dir, "article-1", "platform-1")
            with self.assertRaises(ValueError):
                update_platform_review(out_dir, "zhihu", "approved", run_id="wrong")


if __name__ == "__main__":
    unittest.main()
