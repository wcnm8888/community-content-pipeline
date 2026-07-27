"""Small CLI used by local/manual tooling to record a platform review event."""

import argparse
import json
from pathlib import Path

from platform_review import update_platform_review


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("platform")
    parser.add_argument("status")
    parser.add_argument("--note", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args()
    record = update_platform_review(ROOT / "out", args.platform, args.status, args.note, args.run_id)
    print(json.dumps({"ok": True, "platform": args.platform, "status": record["platforms"][args.platform]["status"], "overall_status": record["overall_status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
