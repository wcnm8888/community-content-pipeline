import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SchedulerScriptTests(unittest.TestCase):
    def test_daily_runner_has_preflight_worker_and_mutex(self):
        content = (ROOT / "scripts" / "run_daily_digest.ps1").read_text(encoding="utf-8")
        self.assertIn("preflight.ps1", content)
        self.assertIn("start_worker.ps1", content)
        self.assertIn("ContentPipelineDailyDigest", content)
        self.assertIn("Daily digest failed", content)

    def test_worker_startup_uses_health_check_and_does_not_stop_unknown_process(self):
        content = (ROOT / "scripts" / "start_worker.ps1").read_text(encoding="utf-8")
        self.assertIn("/health", content)
        self.assertIn("127.0.0.1", content)
        self.assertIn("Port $port is occupied", content)
        self.assertNotIn("Stop-Process", content)

    def test_preflight_does_not_print_credential_values(self):
        content = (ROOT / "scripts" / "preflight.ps1").read_text(encoding="utf-8")
        self.assertIn("DEEPSEEK_API_KEY", content)
        self.assertIn("The key value was not displayed", content)
        self.assertNotIn("Write-Output $Matches[2]", content)

    def test_publish_browser_state_handles_non_json_and_page_errors(self):
        content = (ROOT / "scripts" / "publish" / "common.ps1").read_text(encoding="utf-8")
        self.assertIn("returned a non-JSON result", content)
        self.assertIn("const result = {", content)
        self.assertIn("result.errors.push('page state: ' + error.message)", content)


if __name__ == "__main__":
    unittest.main()
