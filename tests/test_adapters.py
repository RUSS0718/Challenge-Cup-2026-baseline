"""Offline contracts for Intern and DeepAgents product adapters."""

from __future__ import annotations

import unittest

from showcase.adapters import (
    AdapterError,
    DeepAgentsAdapter,
    InternAgentAdapter,
    InternModelAdapter,
)
from showcase.run_service import RunRequest


class FakeClient:
    def __init__(self, responses=None, error=None):
        self.responses = iter(responses or [])
        self.error = error
        self.model = "intern-test"
        self.calls = []

    def chat(self, messages, temperature=0.2, max_tokens=4096, **kwargs):
        self.calls.append((messages, temperature, max_tokens, kwargs))
        if self.error is not None:
            raise self.error
        return next(self.responses)


class AdapterTest(unittest.TestCase):
    def test_intern_response_can_request_registered_tool(self):
        client = FakeClient(['{"tool_call":{"name":"python_math","arguments":{"code":"1+1"}}}'])
        adapter = InternAgentAdapter(InternModelAdapter(client))
        decision = adapter.decide({"problem": "计算 1+1"})
        self.assertEqual("tool", decision.kind)
        self.assertEqual("python_math", decision.tool_name)
        self.assertEqual({"code": "1+1"}, dict(decision.tool_arguments))
        self.assertEqual("intern-test", client.model)

    def test_missing_or_provider_errors_are_structured(self):
        adapter = InternAgentAdapter(InternModelAdapter(FakeClient(error=RuntimeError("secret"))))
        decision = adapter.decide({"problem": "题目"})
        self.assertEqual("failure", decision.kind)
        self.assertEqual("adapter_error", decision.error_category)
        self.assertNotIn("secret", decision.summary)

    def test_deepagents_adapter_uses_product_result_shape_with_fake_client(self):
        client = FakeClient(["答案是 2"])
        adapter = DeepAgentsAdapter(client)
        result = adapter.run(RunRequest(problem="1+1"))
        self.assertEqual("答案是 2", result.final_response)

    def test_deepagents_adapter_runs_product_tool_request_then_continues(self):
        client = FakeClient(
            [
                '{"tool_call":{"name":"double","arguments":{"value":2}}}',
                "工具结果已收到，最终答案是 4",
            ]
        )
        calls = []

        def double(value: int) -> str:
            calls.append(value)
            return str(value * 2)

        result = DeepAgentsAdapter(client, tools=[double]).run(RunRequest(problem="计算 2*2"))
        self.assertEqual([2], calls)
        self.assertIn("最终答案是 4", result.final_response)

    def test_deepagents_adapter_keeps_dependency_failure_actionable(self):
        # The installed local environment supplies DeepAgents; this assertion
        # only documents the public category if a clean Showcase env omits it.
        try:
            DeepAgentsAdapter(FakeClient(["ok"]))
        except AdapterError as exc:
            self.assertEqual("showcase_dependency_missing", exc.category)


if __name__ == "__main__":
    unittest.main()
