import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import scripts.generate_platform_versions as generator


class PlatformBindingTests(unittest.TestCase):
    def test_knowledge_share_review_selects_knowledge_article(self):
        with tempfile.TemporaryDirectory() as directory:
            original = generator.OUT_DIR
            generator.OUT_DIR = Path(directory)
            try:
                (generator.OUT_DIR / "draft-latest.md").write_text("# Daily", encoding="utf-8")
                (generator.OUT_DIR / "knowledge-share-latest.md").write_text("# Knowledge", encoding="utf-8")
                path = generator.resolve_article_path({"content_kind": "knowledge_share"})
                self.assertEqual(path.name, "knowledge-share-latest.md")
            finally:
                generator.OUT_DIR = original


if __name__ == "__main__":
    unittest.main()
