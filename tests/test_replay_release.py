"""Replay artifact and credential-free release gate contracts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from showcase.replay import load_replay, write_sample_replay

ROOT = Path(__file__).resolve().parents[1]


class ReplayReleaseTest(unittest.TestCase):
    def test_checked_in_replay_is_explicit_and_redacted(self):
        path = ROOT / "docs" / "replay" / "showcase-replay-v0.1.json"
        replay = load_replay(path)
        self.assertEqual("replay", replay["run_mode"])
        serialized = json.dumps(replay, ensure_ascii=False).lower()
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("full_image", serialized)

    def test_sample_replay_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "replay.json"
            written = write_sample_replay(path)
            loaded = load_replay(path)
            self.assertEqual("replay", loaded["run_mode"])
            self.assertEqual(written["run"]["run_id"], loaded["run"]["run_id"])

    def test_release_gate_is_credential_free(self):
        if os.environ.get("SHOWCASE_RELEASE_GATE") == "1":
            self.skipTest("release gate is already running")
        result = subprocess.run(
            [sys.executable, "scripts/check_showcase_release.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("showcase_release=PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
