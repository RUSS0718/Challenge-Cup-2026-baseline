"""Protect the exact runtime contents of the official 88-score baseline."""

import hashlib
import json
from pathlib import Path
import unittest


class BaselineSnapshotTest(unittest.TestCase):
    """Verify the dependency closure is present and matches the exported baseline."""

    def test_runtime_files_match_frozen_baseline(self):
        """Reject accidental runtime edits or missing modules during packaging."""
        root = Path(__file__).resolve().parents[1]
        baseline = json.loads((root / "BASELINE.json").read_text(encoding="utf-8"))
        self.assertEqual(11, len(baseline["files"]))
        for name, expected in baseline["files"].items():
            with self.subTest(file=name):
                self.assertEqual(expected, hashlib.sha256((root / name).read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
