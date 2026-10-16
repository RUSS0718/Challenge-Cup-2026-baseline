"""SQLite-backed graph continuation contract."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from showcase.graph import AgentDecision, LangGraphExecutionLoop, LoopBudget, ToolExecutionResult
from showcase.run_service import RunService


class AgentSequence:
    def __init__(self, decisions):
        self.decisions = iter(decisions)

    def decide(self, _state):
        return next(self.decisions)


class ToolSequence:
    def __init__(self, results):
        self.results = iter(results)

    def invoke(self, _name, _arguments):
        return next(self.results)


class GraphServiceTest(unittest.TestCase):
    def test_sqlite_checkpoint_resume_runs_graph_and_keeps_failure_event(self):
        with tempfile.TemporaryDirectory() as directory:
            loop = LangGraphExecutionLoop(
                AgentSequence([AgentDecision.tool("python", {}), AgentDecision.final("recovered")]),
                ToolSequence([ToolExecutionResult(status="timeout", error_category="tool_timeout")]),
                budget=LoopBudget(max_retries=0),
            )
            service = RunService(
                execution_loop=loop,
                database_path=Path(directory) / "runs.sqlite3",
            )
            first = service.create_run({"problem": "计算"})
            self.assertEqual("NEEDS_REVIEW", first["status"])
            checkpoint = service.get_checkpoint(first["run_id"])
            self.assertEqual("NEEDS_REVIEW", checkpoint["status"])
            resumed = service.resume_run(first["run_id"])
            self.assertEqual("COMPLETED", resumed["status"])
            self.assertEqual("recovered", resumed["final_response"])
            events = service.get_events(first["run_id"])
            self.assertIn("tool_completed", [event["type"] for event in events])
            self.assertIn("run_resumed", [event["type"] for event in events])
            service.close()


if __name__ == "__main__":
    unittest.main()
