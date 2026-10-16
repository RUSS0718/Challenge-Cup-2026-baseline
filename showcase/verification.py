"""Replaceable lightweight verification hook for showcase evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Protocol

VerificationStatus = Literal["pass", "conflict", "unknown"]


@dataclass(frozen=True)
class VerificationResult:
    """Evidence about a check, never a claim of mathematical proof."""

    status: VerificationStatus
    findings: tuple[str, ...] = ()
    checker: str = "lightweight_v0"


class VerificationHook(Protocol):
    """Protocol for future research-grade verification implementations."""

    def verify(self, snapshot: dict[str, Any], tool_results: list[dict[str, Any]]) -> VerificationResult:
        """Check one product result and return pass/conflict/unknown."""


class LightweightVerificationHook:
    """Check output shape, tool status, and obvious single-number conflicts."""

    def verify(
        self,
        snapshot: dict[str, Any],
        tool_results: list[dict[str, Any]] | None = None,
    ) -> VerificationResult:
        findings: list[str] = []
        final_response = snapshot.get("final_response")
        if not isinstance(final_response, str) or not final_response.strip():
            return VerificationResult("conflict", ("final_response_missing",))
        results = tool_results or []
        failed_tools = [
            str(result.get("name", "unknown"))
            for result in results
            if result.get("status") not in {None, "success"}
        ]
        if failed_tools:
            findings.append(f"tool_failure:{','.join(failed_tools)}")
        numeric_conflict = _numeric_conflict(final_response, results)
        if numeric_conflict:
            findings.append(numeric_conflict)
        if findings:
            return VerificationResult("conflict", tuple(findings))
        if not results:
            return VerificationResult("unknown", ("no_tool_evidence",))
        return VerificationResult("pass", ("shape_and_tool_consistency_ok",))


def _numeric_conflict(final_response: str, tool_results: list[dict[str, Any]]) -> str | None:
    final_numbers = _numbers(final_response)
    if len(final_numbers) != 1:
        return None
    for result in tool_results:
        summary = result.get("result_summary")
        if not isinstance(summary, str):
            continue
        tool_numbers = _numbers(summary)
        if len(tool_numbers) == 1 and tool_numbers[0] != final_numbers[0]:
            return f"numeric_conflict:final={final_numbers[0]} tool={tool_numbers[0]}"
    return None


def _numbers(text: str) -> list[str]:
    return re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])", text)


__all__ = ["LightweightVerificationHook", "VerificationHook", "VerificationResult"]
