import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DryRunDiagnosticsTests(unittest.TestCase):
    def test_publish_scripts_persist_dryrun_results(self):
        common = (ROOT / "scripts" / "publish" / "common.ps1").read_text(encoding="utf-8")
        runner = (ROOT / "scripts" / "publish_daily.ps1").read_text(encoding="utf-8")
        self.assertIn("dryrun-latest.json", common)
        self.assertIn("Write-DryRunPlatformResult", common)
        self.assertIn("Save-DryRunRecord $context", runner)
        self.assertIn('"needs_manual"', common)

    def test_platform_page_has_dryrun_status_and_retry_endpoint(self):
        renderer = (ROOT / "scripts" / "render_platform_pack_html.py").read_text(encoding="utf-8")
        worker = (ROOT / "scripts" / "worker_server.py").read_text(encoding="utf-8")
        self.assertIn("dryrun-latest.json", renderer)
        self.assertIn("data-dryrun-retry", renderer)
        self.assertIn("http://localhost:8020/dryrun", renderer)
        self.assertIn('self.path == "/dryrun"', worker)
        self.assertIn("unsupported platform", worker)

    def test_renderer_accepts_powershell_utf8_bom(self):
        renderer = (ROOT / "scripts" / "render_platform_pack_html.py").read_text(encoding="utf-8")
        self.assertIn('encoding="utf-8-sig"', renderer)


if __name__ == "__main__":
    unittest.main()
