"""Cross-platform repository check used by local setup and CI."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str]) -> None:
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the credential-free MathAgent repository checks")
    parser.add_argument("--offline", action="store_true", help="keep the workspace check credential-free")
    args = parser.parse_args()

    workspace = [sys.executable, "scripts/check_workspace.py"]
    if args.offline:
        workspace.append("--offline")
    _run(workspace)
    _run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"])
    _run([sys.executable, "demo_server.py", "--help"])
    _run([sys.executable, "showcase_server.py", "--help"])
    print("repository_check=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
