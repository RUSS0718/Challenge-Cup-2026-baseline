"""Contract tests for the product-side showcase Run service."""

from __future__ import annotations

import subprocess
import sys
import unittest

from showcase.run_service import (
    FakeAgentAdapter,
    RunNotFoundError,
    RunService,
    RunValidationError,
)


class RecordingAgent(FakeAgentAdapter):
    """Keep adapter calls visible so validation can be tested at the seam."""

    def __init__(self) -> None:
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        return super().run(request)


class ShowcaseRunServiceTest(unittest.TestCase):
    """Exercise the minimum public Run application contract."""

    def setUp(self) -> None:
        self.agent = RecordingAgent()
        self.service = RunService(agent=self.agent)

    def test_valid_request_creates_unique_completed_run_snapshot(self) -> None:
        first = self.service.create_run({"problem": "计算 1 + 1"})
        second = self.service.create_run({"problem": "计算 2 + 2"})

        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertEqual("showcase_mvp", first["profile"])
        self.assertEqual("COMPLETED", first["status"])
        self.assertEqual("synthesis", first["stage"])
        self.assertTrue(first["final_response"])
        self.assertEqual(first, self.service.get_run(first["run_id"]))
        self.assertEqual(2, len(self.agent.requests))

    def test_invalid_request_is_rejected_before_agent_call(self) -> None:
        with self.assertRaisesRegex(RunValidationError, "problem_must_be_non_empty") as raised:
            self.service.create_run({"problem": "  "})

        self.assertEqual("problem_must_be_non_empty", raised.exception.category)
        self.assertEqual([], self.agent.requests)

        with self.assertRaisesRegex(RunValidationError, "problem_must_be_string"):
            self.service.create_run({"problem": 1})
        self.assertEqual([], self.agent.requests)

    def test_snapshot_contains_redacted_input_reference_and_error_slot(self) -> None:
        snapshot = self.service.create_run(
            {"problem": "求方程的根", "metadata": {"source": "test"}, "asset_refs": ["asset-1"]}
        )

        self.assertNotIn("求方程的根", snapshot)
        self.assertEqual("text", snapshot["input_ref"]["kind"])
        self.assertEqual(5, snapshot["input_ref"]["length"])
        self.assertEqual(["asset-1"], snapshot["asset_refs"])
        self.assertIsNone(snapshot["error"])

    def test_missing_run_has_stable_not_found_category(self) -> None:
        with self.assertRaisesRegex(RunNotFoundError, "run_not_found") as raised:
            self.service.get_run("run_missing")

        self.assertEqual("run_not_found", raised.exception.category)

    def test_health_is_credential_free_and_does_not_call_agent(self) -> None:
        self.assertEqual(
            {
                "status": "ok",
                "service": "showcase_run",
                "profile": "showcase_mvp",
            },
            self.service.health(),
        )
        self.assertEqual([], self.agent.requests)

    def test_official_import_does_not_load_product_package(self) -> None:
        script = "import sys; import user_agent; print('showcase' in sys.modules)"
        result = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual("False", result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
