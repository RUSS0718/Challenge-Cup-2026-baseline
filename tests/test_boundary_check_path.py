"""Exercise path-specific requests through the official entry without model calls."""

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from implementations.candidates.sl_v3_cont import user_agent as solver
from user_agent import ReasoningAgent


BOUNDARY_MARKER = "本路求解重点：条件、解集与边界"
PROBLEM = "Determine the number of configurations satisfying all stated conditions."


class TimedClient:
    """Advance a virtual solve clock while recording complete request payloads."""

    def __init__(self, responses, seconds=60.0):
        """Own a response sequence and deterministic per-request duration."""
        self.responses = iter(responses)
        self.seconds = seconds
        self.now = 100.0
        self.calls = []

    def chat(self, messages, temperature, max_tokens, **kwargs):
        """Record request bytes before returning or raising a scripted outcome."""
        self.calls.append({"messages": deepcopy(messages), "temperature": temperature,
                           "max_tokens": max_tokens, **kwargs})
        self.now += self.seconds
        response = next(self.responses)
        if isinstance(response, BaseException):
            raise response
        return response


class BoundaryCheckPathTest(unittest.TestCase):
    """Keep blind path-two prompting separate from scheduling and selection."""

    def solve(self, client, agent=None, problem=PROBLEM):
        """Use the real entry and real elapsed-time gates against a virtual clock."""
        agent = agent or ReasoningAgent(client=client)
        with patch.object(solver.time, "monotonic", side_effect=lambda: client.now), \
                patch("user_agent.threading.current_thread", return_value=object()):
            result = agent.solve(problem, {"idx": 7})
        json.dumps(result, ensure_ascii=False)
        return agent, result

    def test_only_first_extra_path_changes_prompt_and_votes_normally(self):
        """The same three-call plan must alter path two only, retaining majority voting."""
        client = TimedClient(["最终答案：137", "最终答案：139", "最终答案：139"])
        agent, result = self.solve(client)
        self.assertEqual(3, len(client.calls))
        self.assertEqual([0.2, 0.6, 0.6], [call["temperature"] for call in client.calls])
        self.assertEqual([16384] * 3, [call["max_tokens"] for call in client.calls])
        self.assertEqual([True] * 3, [call["thinking_mode"] for call in client.calls])
        self.assertEqual(solver.SYSTEM_PROMPT, client.calls[0]["messages"][0]["content"])
        self.assertIn(BOUNDARY_MARKER, client.calls[1]["messages"][0]["content"])
        self.assertEqual(client.calls[0]["messages"], client.calls[2]["messages"])
        for call in client.calls[1:]:
            self.assertEqual(["system", "user"], [message["role"] for message in call["messages"]])
            self.assertEqual(client.calls[0]["messages"][1], call["messages"][1])
            self.assertNotIn("137", json.dumps(call["messages"]))
        self.assertEqual(1150.0, agent._solve_budget_seconds)
        self.assertEqual(1250.0, agent._solve_deadline_at)
        self.assertEqual(3, agent._model_calls)
        self.assertEqual(0.2, agent.config.temperature)
        self.assertEqual("139", result["final_response"])
        selection = next(trace["content"]["selection"] for trace in result["trace"]
                         if trace["step"] == "adaptive_rounds")
        self.assertEqual(2, selection["selected_path"])
        self.assertEqual(2, selection["agreed"])

    def test_fast_primary_keeps_existing_single_path_gate(self):
        """A fast answer must not start an extra request just to use the new prompt."""
        client = TimedClient(["最终答案：137"], seconds=10)
        _, result = self.solve(client)
        self.assertEqual(1, len(client.calls))
        self.assertNotIn(BOUNDARY_MARKER, client.calls[0]["messages"][0]["content"])
        self.assertEqual("137", result["final_response"])

    def test_new_solve_resets_path_and_prompt_on_reused_agent(self):
        """No path-specific prompt or previous answer may leak into the next problem."""
        client = TimedClient(["最终答案：137", "最终答案：139", "最终答案：139"] * 2)
        agent, _ = self.solve(client)
        self.solve(client, agent, "Determine the number for a new independent problem.")
        self.assertEqual(6, len(client.calls))
        self.assertEqual([False, True, False] * 2, [BOUNDARY_MARKER in call["messages"][0]["content"]
                                                  for call in client.calls])
        self.assertNotIn(PROBLEM, json.dumps(client.calls[3]["messages"]))
        self.assertEqual(3, agent._model_calls)

    def test_second_path_failure_does_not_change_third_path_prompt(self):
        """Handled provider errors must preserve the baseline fallback and next path."""
        client = TimedClient(["最终答案：137", RuntimeError("provider unavailable"), "最终答案：137"])
        _, result = self.solve(client)
        self.assertEqual(3, len(client.calls))
        self.assertEqual(client.calls[0]["messages"], client.calls[2]["messages"])
        self.assertEqual("137", result["final_response"])

    def test_second_path_continuation_remains_local_and_third_is_default(self):
        """Continuations inherit their own path context, never the first path answer."""
        client = TimedClient(["最终答案：137", "尚未得到结论", "最终答案：139", "最终答案：139"])
        _, result = self.solve(client)
        self.assertEqual(4, len(client.calls))
        self.assertIn(BOUNDARY_MARKER, client.calls[1]["messages"][0]["content"])
        self.assertEqual(client.calls[1]["messages"][0], client.calls[2]["messages"][0])
        self.assertNotIn("137", json.dumps(client.calls[2]["messages"]))
        self.assertEqual(client.calls[0]["messages"], client.calls[3]["messages"])
        self.assertEqual(solver.FULL_REASONING_CONTINUATION_MAX_TOKENS, client.calls[2]["max_tokens"])
        self.assertEqual("139", result["final_response"])

    def test_all_paths_share_the_existing_six_call_limit(self):
        """Two requests per path must use the original shared cap and deadline."""
        client = TimedClient(["尚未得到结论", "最终答案：139"] * 3)
        agent, result = self.solve(client)
        self.assertEqual(solver.MAX_MODEL_CALLS, len(client.calls))
        self.assertEqual(6, agent._model_calls)
        self.assertEqual(1250.0, agent._solve_deadline_at)
        self.assertEqual([False, False, True, True, False, False],
                         [BOUNDARY_MARKER in call["messages"][0]["content"] for call in client.calls])
        self.assertEqual("139", result["final_response"])

    def test_forced_closure_protocol_is_retained_on_every_path(self):
        """The optional checkpoint protocol must remain appended after each path prompt."""
        client = TimedClient(["最终答案：137", "最终答案：139", "最终答案：139"])
        agent = ReasoningAgent(client=client, config=solver.AgentConfig(enable_forced_closure=True))
        self.solve(client, agent)
        self.assertEqual(3, len(client.calls))
        for call in client.calls:
            self.assertTrue(call["messages"][0]["content"].endswith(solver.CLOSURE_PROMPT_SUFFIX))


if __name__ == "__main__":
    unittest.main()
