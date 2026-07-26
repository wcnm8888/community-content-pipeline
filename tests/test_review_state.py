import json
import tempfile
import unittest
from pathlib import Path

from scripts.review_state import update_review_files, write_review_record


class ReviewStateTests(unittest.TestCase):
    def test_write_defaults_to_pending_human_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            dated_dir = out_dir / "2026-07-27"
            dated_dir.mkdir()
            write_review_record(
                {"quality_score": 90, "safe_to_sync": True, "summary": "ok"},
                out_dir / "article-review-latest.json",
                out_dir / "article-review-latest.md",
                "20260727-120000",
                dated_dir / "article-review-20260727-120000.json",
                dated_dir / "article-review-20260727-120000.md",
            )
            review = json.loads((out_dir / "article-review-latest.json").read_text(encoding="utf-8"))
            self.assertEqual(review["run_id"], "20260727-120000")
            self.assertEqual(review["review_status"], "pending")
            self.assertIsNone(review["human_review"]["reviewed_at"])

    def test_update_mirrors_latest_and_dated_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            dated_dir = out_dir / "2026-07-27"
            dated_dir.mkdir()
            dated_json = dated_dir / "article-review-20260727-120000.json"
            write_review_record(
                {"quality_score": 90, "safe_to_sync": True},
                out_dir / "article-review-latest.json",
                out_dir / "article-review-latest.md",
                "20260727-120000",
                dated_json,
                dated_dir / "article-review-20260727-120000.md",
            )
            updated = update_review_files(out_dir, "approved", "人工确认通过", "20260727-120000")
            self.assertEqual(updated["review_status"], "approved")
            self.assertEqual(updated["human_review"]["note"], "人工确认通过")
            dated = json.loads(dated_json.read_text(encoding="utf-8"))
            self.assertEqual(dated["review_status"], "approved")
            self.assertIn("人工审核状态：approved", (dated_json.with_suffix(".md")).read_text(encoding="utf-8"))

    def test_stale_run_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            write_review_record(
                {"quality_score": 90},
                out_dir / "article-review-latest.json",
                out_dir / "article-review-latest.md",
                "20260727-120000",
            )
            with self.assertRaises(ValueError):
                update_review_files(out_dir, "approved", run_id="old-run")


if __name__ == "__main__":
    unittest.main()
