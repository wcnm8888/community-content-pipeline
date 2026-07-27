import json
import tempfile
import unittest
from pathlib import Path

from scripts.render_article_review_html import load_latest_article


class ReviewArticleSourceTests(unittest.TestCase):
    def test_knowledge_review_selects_knowledge_share_article(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            import scripts.render_article_review_html as renderer
            original_out = renderer.OUT_DIR
            renderer.OUT_DIR = root
            try:
                (root / "article-review-latest.json").write_text(json.dumps({"content_kind": "knowledge_share"}), encoding="utf-8")
                (root / "draft-latest.md").write_text("# Daily", encoding="utf-8")
                (root / "knowledge-share-latest.md").write_text("# Knowledge", encoding="utf-8")
                article, filename = load_latest_article()
                self.assertEqual(filename, "knowledge-share-latest.md")
                self.assertEqual(article, "# Knowledge")
            finally:
                renderer.OUT_DIR = original_out


if __name__ == "__main__":
    unittest.main()
