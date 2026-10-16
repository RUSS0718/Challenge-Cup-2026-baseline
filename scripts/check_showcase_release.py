"""Run the credential-free V0.1 Showcase release gate."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPLAY = ROOT / "docs" / "replay" / "showcase-replay-v0.1.json"


def main() -> int:
    checks = [
        [sys.executable, "scripts/check_workspace.py", "--offline"],
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
        [sys.executable, "demo_server.py", "--help"],
        [sys.executable, "showcase_server.py", "--help"],
    ]
    for command in checks:
        environment = os.environ.copy()
        if command[1:4] == ["-m", "unittest", "discover"]:
            environment["SHOWCASE_RELEASE_GATE"] = "1"
        completed = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, check=False, env=environment
        )
        if completed.returncode != 0:
            print(f"showcase_release=FAIL command={' '.join(command)}")
            print(completed.stdout)
            print(completed.stderr)
            return completed.returncode or 1
    try:
        payload = json.loads(REPLAY.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"showcase_release=FAIL replay={type(exc).__name__}")
        return 1
    serialized = json.dumps(payload, ensure_ascii=False)
    for marker in (
        "api_key",
        "authorization",
        "prompt",
        "hidden_answer",
        "image_bytes",
        "image_base64",
        "full_image",
        "full_image_bytes",
        "full_image_base64",
    ):
        if marker in serialized.lower():
            print(f"showcase_release=FAIL sensitive_marker={marker}")
            return 1
    if payload.get("run_mode") != "replay":
        print("showcase_release=FAIL replay_mode_missing")
        return 1
    print("showcase_release=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
