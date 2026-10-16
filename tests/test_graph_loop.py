"""Contract tests for the bounded LangGraph showcase loop."""

from __future__ import annotations

import unittest

from showcase.graph import AgentDecision, LangGraphExecutionLoop, LoopBudget, ToolExecutionResult


class ScriptedAgent:
    def __init__(self, decisions):
        self.decisions = iter(decisions)

    def decide(self, _state):
        return next(self.decisions)


class ScriptedTools:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    def invoke(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        return next(self.results)


class LangGraphLoopTest(unittest.TestCase):
    def test_dynamic_tool_call_then_final_answer(self):
        tools = ScriptedTools([ToolExecutionResult.success(value=2, result_summary="2")])
        loop = LangGraphExecutionLoop(
            ScriptedAgent([AgentDecision.tool("python", {"code": "1+1"}), AgentDecision.final("2")]),
            tools,
        )

        result = loop.run({"run_id": "run_success", "problem": "计算 1+1"})

        self.assertEqual("COMPLETED", result["status"])
        self.assertEqual("completed", result["stage"])
        self.assertEqual("2", result["final_response"])
        self.assertEqual([("python", {"code": "1+1"})], tools.calls)
        self.assertEqual(
            [
                "run_received",
                "agent_decision",
                "tool_completed",
                "agent_decision",
                "verification_completed",
                "run_terminal",
            ],
                         [event["type"] for event in result["events"]])

    def test_tool_failure_is_reviewable_and_resume_keeps_failure_event(self):
        tools = ScriptedTools([
            ToolExecutionResult(status="timeout", error_category="tool_timeout"),
        ])
        loop = LangGraphExecutionLoop(
            ScriptedAgent([AgentDecision.tool("python", {})]),
            tools,
        )
        first = loop.run({"run_id": "run_retry", "problem": "计算"})
        self.assertEqual("NEEDS_REVIEW", first["status"])
        self.assertEqual("tool_timeout", first["error"]["category"])

        resumed_loop = LangGraphExecutionLoop(
            ScriptedAgent([AgentDecision.final("recovered")]),
            ScriptedTools([]),
        )
        resumed = resumed_loop.resume(first, thread_id="run_retry-resume")
        self.assertEqual("COMPLETED", resumed["status"])
        self.assertEqual("recovered", resumed["final_response"])
        self.assertIn("tool_completed", [event["type"] for event in resumed["events"]])
        self.assertIn("run_resumed", [event["type"] for event in resumed["events"]])

    def test_step_budget_has_terminal_explanation(self):
        loop = LangGraphExecutionLoop(
            ScriptedAgent([AgentDecision.tool("never", {})] * 5),
            ScriptedTools([ToolExecutionResult.success()] * 5),
            budget=LoopBudget(max_steps=2, max_tools=5),
        )
        result = loop.run({"run_id": "run_budget", "problem": "循环"})
        self.assertEqual("FAILED", result["status"])
        self.assertEqual("budget_exhausted", result["error"]["category"])


if __name__ == "__main__":
    unittest.main()
