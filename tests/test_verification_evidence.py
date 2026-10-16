"""Contracts for lightweight verification and Evidence Pack export."""

from __future__ import annotations

import json
import unittest

from showcase.evidence import EvidencePackExporter
from showcase.verification import LightweightVerificationHook


class VerificationEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.snapshot = {
            "run_id": "run_1",
            "profile": "showcase_mvp",
            "status": "COMPLETED",
            "stage": "completed",
            "input_ref": {"kind": "text", "length": 4, "sha256": "abc"},
            "asset_refs": ["asset_1"],
            "final_response": "答案是 2",
            "error": None,
        }

    def test_hook_returns_pass_conflict_and_unknown(self):
        hook = LightweightVerificationHook()
        self.assertEqual("pass", hook.verify(self.snapshot, [{"name": "python", "status": "success", "result_summary": "2"}]).status)
        self.assertEqual("conflict", hook.verify(self.snapshot, [{"name": "python", "status": "success", "result_summary": "3"}]).status)
        self.assertEqual("unknown", hook.verify(self.snapshot, []).status)

    def test_evidence_pack_is_json_serializable_and_redacted(self):
        exporter = EvidencePackExporter()
        pack = exporter.export(
            self.snapshot | {"final_response": "答案是 2", "prompt": "private"},
            events=[
                {"sequence": 1, "type": "run_completed", "summary": "safe", "prompt": "hidden"}
            ],
            tool_results=[
                {
                    "name": "python_math",
                    "status": "success",
                    "parameter_summary": '{"code":{"type":"str","length":3}}',
                    "result_summary": "2",
                }
            ],
            verification={"status": "pass", "findings": []},
            artifacts=[
                {
                    "asset_id": "asset_1",
                    "image_bytes": "FULL_IMAGE",
                    "full_image_bytes": "FULL_IMAGE_VARIANT",
                }
            ],
        )
        json.dumps(pack, ensure_ascii=False)
        serialized = exporter.to_json(pack)
        self.assertNotIn("private", serialized)
        self.assertNotIn("hidden", serialized)
        self.assertNotIn("FULL_IMAGE", serialized)
        self.assertNotIn("FULL_IMAGE_VARIANT", serialized)
        self.assertEqual("pass", pack["verification"]["status"])
        self.assertEqual("event_1", pack["timeline"][0]["evidence_id"])
        self.assertEqual("planned", pack["feature_status"]["multimodal"])


if __name__ == "__main__":
    unittest.main()
