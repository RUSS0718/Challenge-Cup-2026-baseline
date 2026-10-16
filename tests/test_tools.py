"""Contract tests for the showcase Tool Registry and Python math tool."""

from __future__ import annotations

import subprocess
import time
import unittest
from unittest.mock import patch

from showcase.tools import PythonMathTool, ToolRegistry


class ToolRegistryTest(unittest.TestCase):
    def test_registry_invokes_registered_tool_and_returns_summary(self):
        registry = ToolRegistry(max_calls=1)
        registry.register("double", lambda args: int(args["value"]) * 2, capabilities=("math",))
        result = registry.invoke("double", {"value": 3})
        self.assertEqual("success", result.status)
        self.assertEqual("6", result.result_summary)
        self.assertEqual("math", registry.describe()[0]["capabilities"][0])

        exhausted = registry.invoke("double", {"value": 3})
        self.assertEqual("rejected", exhausted.status)
        self.assertEqual("tool_budget_exhausted", exhausted.error_category)

    def test_profile_permission_and_timeout_are_structured(self):
        registry = ToolRegistry(profile="official")
        registry.register("showcase_only", lambda _args: "ok")
        denied = registry.invoke("showcase_only", {})
        self.assertEqual("tool_not_permitted_for_profile", denied.error_category)

        slow = ToolRegistry()
        slow.register("slow", lambda _args: (time.sleep(0.05), "ok")[1], timeout_seconds=0.001)
        self.assertEqual("timeout", slow.invoke("slow", {}).status)


class PythonMathToolTest(unittest.TestCase):
    def test_sympy_expression_runs_in_subprocess(self):
        result = PythonMathTool().invoke({"code": "import sympy as sp\nprint(sp.factor(12))"})
        self.assertEqual("success", result.status)
        self.assertEqual("12", result.result_summary)

    def test_dangerous_import_and_file_access_are_rejected(self):
        for code in ("import os\nprint(os.listdir('.'))", "print(open('secret.txt').read())"):
            result = PythonMathTool().invoke({"code": code})
            self.assertEqual("rejected", result.status)
            self.assertIn(
                result.error_category,
                {"import_not_allowed", "name_not_allowed", "call_not_allowed"},
            )

    def test_subprocess_timeout_is_explicit(self):
        with patch(
            "showcase.tools.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="python", timeout=3),
        ):
            result = PythonMathTool().invoke({"code": "print(1)"})
        self.assertEqual("timeout", result.status)
        self.assertEqual("python_timeout", result.error_category)


if __name__ == "__main__":
    unittest.main()
