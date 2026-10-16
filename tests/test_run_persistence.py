"""Persistence contract tests for the showcase Run service."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from showcase.run_service import RunService


class FailingAgent:
    """Raise after the Run has entered the persisted execution state."""

    def run(self, request):
        raise TimeoutError("provider timeout")


class ShowcaseRunPersistenceTest(unittest.TestCase):
    """Exercise the SQLite seam through the public application service."""

    def test_run_events_and_checkpoint_survive_service_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "showcase.sqlite3"
            first = RunService(database_path=database_path)
            snapshot = first.create_run({"problem": "计算 1 + 1"})
            run_id = snapshot["run_id"]
            events_before = first.get_events(run_id)
            checkpoint_before = first.get_checkpoint(run_id)
            first.close()

            second = RunService(database_path=database_path)
            self.assertEqual(snapshot, second.get_run(run_id))
            self.assertEqual(events_before, second.get_events(run_id))
            self.assertEqual(checkpoint_before, second.get_checkpoint(run_id))
            self.assertGreaterEqual(len(events_before), 3)
            self.assertEqual("COMPLETED", checkpoint_before["status"])
            second.close()

    def test_failed_run_event_is_append_only_and_survives_checkpoint_update(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "showcase.sqlite3"
            service = RunService(agent=FailingAgent(), database_path=database_path)
            snapshot = service.create_run({"problem": "求极限"})
            run_id = snapshot["run_id"]
            failure_events = [event for event in service.get_events(run_id) if event["type"] == "run_failed"]
            self.assertEqual(1, len(failure_events))
            failure_event = failure_events[0]

            service.append_event(
                run_id,
                {
                    "type": "resume_requested",
                    "status": "RESUMED",
                    "stage": "solving",
                    "summary": "resume requested",
                },
            )
            service.save_checkpoint(run_id, {"status": "RESUMED", "stage": "solving"})
            events = service.get_events(run_id)
            self.assertIn(failure_event, events)
            self.assertGreater(events[-1]["sequence"], failure_event["sequence"])
            self.assertEqual("RESUMED", service.get_checkpoint(run_id)["status"])
            service.close()

    def test_event_payload_is_redacted_before_storage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = RunService(database_path=Path(directory) / "showcase.sqlite3")
            snapshot = service.create_run({"problem": "不会出现在事件里"})
            event = service.append_event(
                snapshot["run_id"],
                {
                    "type": "tool_call",
                    "summary": "safe summary",
                    "data": {
                        "prompt": "secret prompt",
                        "token": "secret token",
                        "result_summary": "2",
                    },
                },
            )
            serialized = repr(event)
            self.assertNotIn("secret prompt", serialized)
            self.assertNotIn("secret token", serialized)
            self.assertIn("result_summary", serialized)
            leaked = service.append_event(
                snapshot["run_id"],
                {"type": "summary", "summary": "apiKey=SECRET full_prompt=PRIVATE"},
            )
            self.assertNotIn("SECRET", repr(leaked))
            self.assertNotIn("PRIVATE", repr(leaked))
            service.close()


if __name__ == "__main__":
    unittest.main()
