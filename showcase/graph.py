"""LangGraph execution loop for the showcase Run product contract.

The graph deliberately exchanges plain product dictionaries and dataclasses.
LangGraph checkpoint objects and model-specific message types never become part
of the persisted Run snapshot.
"""

from __future__ import annotations

import copy
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypedDict

try:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph
except ImportError as exc:  # pragma: no cover - exercised in a dependency-free install
    InMemorySaver = None  # type: ignore[assignment,misc]
    END = "__end__"
    START = "__start__"
    StateGraph = None  # type: ignore[assignment,misc]
    _LANGGRAPH_IMPORT_ERROR: BaseException | None = exc
else:
    _LANGGRAPH_IMPORT_ERROR = None


DecisionKind = Literal["final", "tool", "review", "failure"]
ToolStatus = Literal["success", "timeout", "rejected", "error"]


class GraphDependencyError(RuntimeError):
    """Raised when the showcase graph is used without its optional dependency."""

    category = "showcase_dependency_missing"


class LoopState(TypedDict, total=False):
    """JSON-compatible state exchanged by graph nodes."""

    run_id: str
    problem: str
    status: str
    stage: str
    step_count: int
    tool_count: int
    retry_count: int
    started_at: float
    pending_tool: dict[str, Any] | None
    tool_results: list[dict[str, Any]]
    events: list[dict[str, Any]]
    final_response: str | None
    error: dict[str, Any] | None
    next_node: str
    resumed: bool


@dataclass(frozen=True)
class AgentDecision:
    """Product-level decision returned by a Planner/Solver adapter."""

    kind: DecisionKind
    final_response: str = ""
    tool_name: str = ""
    tool_arguments: Mapping[str, Any] = field(default_factory=dict)
    summary: str = ""
    error_category: str = "agent_failure"

    @classmethod
    def final(cls, response: str, summary: str = "") -> AgentDecision:
        return cls(kind="final", final_response=response, summary=summary)

    @classmethod
    def tool(cls, name: str, arguments: Mapping[str, Any], summary: str = "") -> AgentDecision:
        return cls(kind="tool", tool_name=name, tool_arguments=dict(arguments), summary=summary)

    @classmethod
    def review(cls, summary: str, error_category: str = "needs_review") -> AgentDecision:
        return cls(kind="review", summary=summary, error_category=error_category)

    @classmethod
    def failure(cls, summary: str, error_category: str = "agent_failure") -> AgentDecision:
        return cls(kind="failure", summary=summary, error_category=error_category)


@dataclass(frozen=True)
class ToolExecutionResult:
    """Normalized product result for one registered tool invocation."""

    status: ToolStatus
    result_summary: str = ""
    value: Any = None
    error_category: str | None = None
    duration_seconds: float = 0.0

    @classmethod
    def success(cls, value: Any = None, result_summary: str = "") -> ToolExecutionResult:
        return cls(status="success", value=value, result_summary=result_summary)


class AgentDecisionProvider(Protocol):
    """Adapter boundary used by the execution loop."""

    def decide(self, state: Mapping[str, Any]) -> AgentDecision | Mapping[str, Any]:
        """Return one product-level decision for the current state."""


class ToolExecutor(Protocol):
    """Minimal tool seam used by the graph."""

    def invoke(self, name: str, arguments: Mapping[str, Any]) -> ToolExecutionResult | Mapping[str, Any]:
        """Execute one registered tool call."""


@dataclass(frozen=True)
class LoopBudget:
    """Hard upper bounds for one graph invocation."""

    max_steps: int = 8
    max_tools: int = 4
    max_retries: int = 1
    max_runtime_seconds: float = 30.0

    def validate(self) -> None:
        if self.max_steps <= 0 or self.max_tools < 0 or self.max_retries < 0:
            raise ValueError("loop_budget_must_be_non_negative")
        if self.max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds_must_be_positive")


class LangGraphExecutionLoop:
    """Run a bounded dynamic Agent/tool loop with explicit terminal states."""

    def __init__(
        self,
        agent: AgentDecisionProvider,
        tools: ToolExecutor,
        *,
        budget: LoopBudget | None = None,
        checkpointer: Any | None = None,
        event_sink: Callable[[str, Mapping[str, Any]], None] | None = None,
        checkpoint_sink: Callable[[str, Mapping[str, Any]], None] | None = None,
    ) -> None:
        if StateGraph is None:
            raise GraphDependencyError("langgraph is required for showcase execution") from _LANGGRAPH_IMPORT_ERROR
        self.agent = agent
        self.tools = tools
        self.budget = budget or LoopBudget()
        self.budget.validate()
        self.event_sink = event_sink
        self.checkpoint_sink = checkpoint_sink
        self.checkpointer = checkpointer if checkpointer is not None else InMemorySaver()
        self._graph = self._build_graph()

    def run(
        self,
        initial_state: Mapping[str, Any],
        *,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute from an initial product state and return a JSON-compatible state."""

        state = _normalize_state(initial_state)
        state.setdefault("started_at", time.monotonic())
        state.setdefault("status", "RUNNING")
        state.setdefault("stage", "planning")
        state.setdefault("next_node", "agent")
        state.setdefault("events", [])
        state.setdefault("tool_results", [])
        if not state["events"]:
            _record_event(state, "run_received", {"status": state["status"], "stage": state["stage"]})
        config = {"configurable": {"thread_id": thread_id or state.get("run_id", "showcase-run")}}
        result = self._graph.invoke(state, config)
        return _copy_state(result)

    def resume(
        self,
        state: Mapping[str, Any],
        *,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """Continue a reviewable state while retaining the original failure event."""

        resumed = _normalize_state(state)
        resumed["resumed"] = True
        resumed["status"] = "RESUMED"
        resumed["stage"] = "solving"
        resumed["error"] = None
        resumed["next_node"] = "agent"
        self._record_and_emit(resumed, "run_resumed", {"status": "RESUMED", "stage": "solving"})
        return self.run(resumed, thread_id=thread_id)

    def _build_graph(self) -> Any:
        builder = StateGraph(LoopState)
        builder.add_node("agent", self._agent_node)
        builder.add_node("tool", self._tool_node)
        builder.add_node("terminal", self._terminal_node)
        builder.add_edge(START, "agent")
        builder.add_conditional_edges(
            "agent",
            lambda state: state.get("next_node", "terminal"),
            {"agent": "agent", "tool": "tool", "terminal": "terminal"},
        )
        builder.add_conditional_edges(
            "tool",
            lambda state: state.get("next_node", "terminal"),
            {"agent": "agent", "terminal": "terminal"},
        )
        builder.add_edge("terminal", END)
        return builder.compile(checkpointer=self.checkpointer)

    def _agent_node(self, state: LoopState) -> dict[str, Any]:
        updated = _normalize_state(state)
        if _budget_exhausted(updated, self.budget):
            _finish_with_error(updated, "budget_exhausted", "Agent loop budget exhausted")
            return updated
        updated["step_count"] = int(updated.get("step_count", 0)) + 1
        updated["stage"] = "running"
        try:
            decision = _normalize_decision(self.agent.decide(updated))
        except Exception as exc:  # noqa: BLE001 - normalize adapter failures for the product
            _finish_with_error(updated, "agent_adapter_error", type(exc).__name__)
            return updated
        self._record_and_emit(
            updated, "agent_decision", {"kind": decision.kind, "summary": decision.summary}
        )
        if decision.kind == "final":
            if not decision.final_response.strip():
                _finish_with_error(updated, "empty_final_response", "Agent returned an empty final response")
            else:
                updated["status"] = "COMPLETED"
                updated["stage"] = "synthesis"
                updated["final_response"] = decision.final_response
                updated["next_node"] = "terminal"
            return updated
        if decision.kind == "tool":
            if not decision.tool_name.strip():
                _finish_with_error(updated, "tool_name_missing", "Agent requested a tool without a name")
            else:
                updated["pending_tool"] = {
                    "name": decision.tool_name,
                    "arguments": dict(decision.tool_arguments),
                }
                updated["next_node"] = "tool"
            return updated
        if decision.kind == "review":
            _finish_with_error(updated, decision.error_category, decision.summary or "Review requested")
            updated["status"] = "NEEDS_REVIEW"
            return updated
        _finish_with_error(updated, decision.error_category, decision.summary or "Agent failed")
        return updated

    def _tool_node(self, state: LoopState) -> dict[str, Any]:
        updated = _normalize_state(state)
        if _budget_exhausted(updated, self.budget):
            _finish_with_error(updated, "budget_exhausted", "Agent loop budget exhausted")
            return updated
        if int(updated.get("tool_count", 0)) >= self.budget.max_tools:
            _finish_with_error(updated, "tool_budget_exhausted", "Tool budget exhausted")
            return updated
        pending = updated.get("pending_tool")
        if not isinstance(pending, Mapping):
            _finish_with_error(updated, "tool_request_missing", "Tool node has no pending request")
            return updated
        name = str(pending.get("name", ""))
        arguments = pending.get("arguments", {})
        if not isinstance(arguments, Mapping):
            _finish_with_error(updated, "tool_arguments_invalid", "Tool arguments must be an object")
            return updated
        started = time.monotonic()
        try:
            result = _normalize_tool_result(self.tools.invoke(name, arguments))
        except Exception as exc:  # noqa: BLE001 - tool failures are data, not process failures
            result = ToolExecutionResult(status="error", error_category=type(exc).__name__)
        result = ToolExecutionResult(
            status=result.status,
            result_summary=result.result_summary,
            value=result.value,
            error_category=result.error_category,
            duration_seconds=result.duration_seconds or round(time.monotonic() - started, 3),
        )
        updated["tool_count"] = int(updated.get("tool_count", 0)) + 1
        tool_record = {
            "name": name,
            "status": result.status,
            "result_summary": result.result_summary,
            "error_category": result.error_category,
            "duration_seconds": result.duration_seconds,
        }
        updated.setdefault("tool_results", []).append(tool_record)
        self._record_and_emit(updated, "tool_completed", tool_record)
        updated["pending_tool"] = None
        if result.status != "success":
            _finish_with_error(updated, result.error_category or f"tool_{result.status}", "Tool call failed")
            updated["status"] = "NEEDS_REVIEW"
            return updated
        updated["next_node"] = "agent"
        return updated

    def _terminal_node(self, state: LoopState) -> dict[str, Any]:
        updated = _normalize_state(state)
        if updated.get("status") not in {"COMPLETED", "NEEDS_REVIEW", "FAILED"}:
            updated["status"] = "FAILED"
            updated["stage"] = "failed"
        updated["next_node"] = "terminal"
        self._record_and_emit(
            updated, "run_terminal", {"status": updated["status"], "stage": updated["stage"]}
        )
        return updated

    def _record_and_emit(
        self, state: LoopState, event_type: str, payload: Mapping[str, Any]
    ) -> None:
        _record_event(state, event_type, payload)
        run_id = state.get("run_id")
        if isinstance(run_id, str) and run_id:
            self._emit(run_id, {"type": event_type, **copy.deepcopy(dict(payload))})

    def _emit(self, run_id: str, event: Mapping[str, Any]) -> None:
        if self.event_sink is not None:
            self.event_sink(run_id, event)
        if self.checkpoint_sink is not None:
            self.checkpoint_sink(run_id, event)


def _normalize_state(state: Mapping[str, Any]) -> LoopState:
    normalized: LoopState = copy.deepcopy(dict(state))  # type: ignore[assignment]
    normalized.setdefault("step_count", 0)
    normalized.setdefault("tool_count", 0)
    normalized.setdefault("retry_count", 0)
    normalized.setdefault("tool_results", [])
    normalized.setdefault("events", [])
    return normalized


def _normalize_decision(value: AgentDecision | Mapping[str, Any]) -> AgentDecision:
    if isinstance(value, AgentDecision):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("agent_decision_must_be_object")
    kind = value.get("kind")
    if kind not in {"final", "tool", "review", "failure"}:
        raise ValueError("agent_decision_kind_invalid")
    return AgentDecision(
        kind=kind,
        final_response=str(value.get("final_response", "")),
        tool_name=str(value.get("tool_name", "")),
        tool_arguments=(value.get("tool_arguments") if isinstance(value.get("tool_arguments"), Mapping) else {}),
        summary=str(value.get("summary", "")),
        error_category=str(value.get("error_category", "agent_failure")),
    )


def _normalize_tool_result(value: ToolExecutionResult | Mapping[str, Any]) -> ToolExecutionResult:
    if isinstance(value, ToolExecutionResult):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("tool_result_must_be_object")
    status = value.get("status")
    if status not in {"success", "timeout", "rejected", "error"}:
        raise ValueError("tool_status_invalid")
    return ToolExecutionResult(
        status=status,
        result_summary=str(value.get("result_summary", "")),
        value=value.get("value"),
        error_category=(str(value["error_category"]) if value.get("error_category") else None),
        duration_seconds=float(value.get("duration_seconds", 0.0) or 0.0),
    )


def _budget_exhausted(state: Mapping[str, Any], budget: LoopBudget) -> bool:
    started_at = float(state.get("started_at", time.monotonic()))
    return int(state.get("step_count", 0)) >= budget.max_steps or (
        time.monotonic() - started_at >= budget.max_runtime_seconds
    )


def _finish_with_error(state: LoopState, category: str, summary: str) -> None:
    state["status"] = "FAILED"
    state["stage"] = "failed"
    state["error"] = {"category": category, "summary": summary}
    state["next_node"] = "terminal"


def _record_event(state: LoopState, event_type: str, payload: Mapping[str, Any]) -> None:
    event = {"type": event_type, **copy.deepcopy(dict(payload))}
    state.setdefault("events", []).append(event)


def _copy_state(state: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(dict(state))


__all__ = [
    "AgentDecision",
    "AgentDecisionProvider",
    "GraphDependencyError",
    "LangGraphExecutionLoop",
    "LoopBudget",
    "LoopState",
    "ToolExecutionResult",
    "ToolExecutor",
]
