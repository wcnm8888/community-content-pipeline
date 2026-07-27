import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from knowledge_share import search_sources, search_tavily


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class TavilySearchTests(unittest.TestCase):
    @patch("knowledge_share.urlopen")
    def test_tavily_response_is_mapped_to_source_candidates(self, urlopen):
        urlopen.return_value = FakeResponse({"results": [{
            "title": "Official MCP documentation",
            "url": "https://modelcontextprotocol.io/",
            "content": "Official documentation for MCP.",
            "score": 0.92,
        }]})
        candidates = search_tavily({"TAVILY_API_KEY": "tvly-test"}, "MCP", "developer use", 5)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].url, "https://modelcontextprotocol.io")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.headers["Authorization"], "Bearer tvly-test")
        self.assertEqual(json.loads(request.data)["max_results"], 5)

    def test_missing_tavily_key_is_actionable(self):
        with self.assertRaisesRegex(RuntimeError, "TAVILY_API_KEY"):
            search_sources({"SEARCH_PROVIDER": "tavily"}, "MCP", "", 5)

    def test_brave_provider_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "uses Tavily"):
            search_sources({"SEARCH_PROVIDER": "brave"}, "MCP", "", 5)


if __name__ == "__main__":
    unittest.main()
