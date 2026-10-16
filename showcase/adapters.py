"""Product-level Intern and DeepAgents adapters.

The adapters normalize provider/framework behavior before it reaches Run state.
They are imported only by the explicit showcase profile and are safe to test
with an injected fake client.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .graph import AgentDecision
from .run_service import AgentResult, RunRequest


class AdapterError(RuntimeError):
    """Sanitized provider/framework failure used by the product surface."""

    def __init__(self, category: str, detail: str = "") -> None:
        super().__init__(category)
        self.category = category
        self.detail = detail


@dataclass(frozen=True)
class ToolRequest:
    """Normalized model-requested tool call."""

    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelResponse:
    """Provider-independent response returned by ``InternModelAdapter``."""

    text: str = ""
    tool_requests: tuple[ToolRequest, ...] = ()
    usage: Mapping[str, Any] = field(default_factory=dict)
    model_id: str = ""
    error_category: str | None = None


class InternModelAdapter:
    """Normalize the existing Intern client without changing its API."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        model_id: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> None:
        self._client = client
        self.model_id = model_id or os.environ.get("INTERN_MODEL", "intern-s2")
        self.temperature = temperature
        self.max_tokens = max_tokens

    def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        tools: Sequence[Mapping[str, Any]] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> ModelResponse:
        """Call the injected/current Intern client and parse safe tool markers."""

        client = self._get_client()
        normalized = [_normalize_message(message) for message in messages]
        kwargs: dict[str, Any] = {
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        # The repository client intentionally has no tools kwarg.  Injected
        # clients may opt in; old clients continue to receive the official text shape.
        if tools and _accepts_keyword(client.chat, "tools"):
            kwargs["tools"] = [dict(tool) for tool in tools]
        try:
            raw = client.chat(normalized, **kwargs)
        except Exception as exc:  # noqa: BLE001 - provider details stay out of events
            category = getattr(exc, "category", None) or (
                "configuration" if type(exc).__name__ == "ChatClientError" else "adapter_error"
            )
            raise AdapterError(str(category), type(exc).__name__) from exc
        text, usage = _extract_response(raw)
        return ModelResponse(
            text=text,
            tool_requests=tuple(_parse_tool_requests(text)),
            usage=usage,
            model_id=getattr(client, "model", self.model_id) or self.model_id,
        )

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from llm_client import InternChatClient

            self._client = InternChatClient()
        except Exception as exc:  # noqa: BLE001 - missing credentials are expected locally
            category = getattr(exc, "category", None) or "configuration"
            raise AdapterError(str(category), type(exc).__name__) from exc
        return self._client


class InternAgentAdapter:
    """Role-level adapter that converts model responses into graph decisions."""

    def __init__(
        self,
        model: InternModelAdapter,
        *,
        role: str = "solver",
        tool_schemas: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        self.model = model
        self.role = role
        self.tool_schemas = tuple(dict(schema) for schema in tool_schemas)

    def decide(self, state: Mapping[str, Any]) -> AgentDecision:
        """Ask Intern for one bounded decision using product-level state only."""

        problem = str(state.get("problem", ""))
        messages = [
            {
                "role": "system",
                "content": (
                    f"You are the {self.role} role. Return a concise final answer, or a JSON "
                    "tool_call object when registered computation is required."
                ),
            },
            {"role": "user", "content": problem},
        ]
        try:
            response = self.model.complete(messages, tools=self.tool_schemas)
        except AdapterError as exc:
            return AgentDecision.failure(
                f"Intern adapter unavailable: {exc.category}",
                error_category=exc.category,
            )
        if response.tool_requests:
            request = response.tool_requests[0]
            return AgentDecision.tool(request.name, request.arguments, summary="Intern requested a tool")
        if not response.text.strip():
            return AgentDecision.failure("Intern returned an empty response", "empty_model_response")
        return AgentDecision.final(response.text, summary=f"model={response.model_id}")

    def run(self, request: RunRequest) -> AgentResult:
        """Provide the RunService AgentAdapter shape for a single model turn."""

        decision = self.decide({"problem": request.problem})
        if decision.kind == "final":
            return AgentResult(final_response=decision.final_response, summary=decision.summary)
        if decision.kind == "tool":
            raise AdapterError("tool_request_requires_execution", decision.tool_name)
        raise AdapterError(decision.error_category, decision.summary)


class InternChatModel:
    """Small LangChain ``BaseChatModel`` bridge used by DeepAgents."""

    def __new__(cls, *args: Any, **kwargs: Any) -> Any:
        try:
            from langchain_core.language_models import BaseChatModel
            from langchain_core.messages import AIMessage
            from langchain_core.outputs import ChatGeneration, ChatResult
            from pydantic import ConfigDict
        except ImportError as exc:  # pragma: no cover - product dependency boundary
            raise AdapterError("showcase_dependency_missing", "langchain-core") from exc

        class _InternChatModel(BaseChatModel):
            model_config = ConfigDict(arbitrary_types_allowed=True)
            client: Any
            model_id: str = "intern-s2"

            @property
            def _llm_type(self) -> str:
                return "intern-showcase"

            def _generate(self, messages: Sequence[Any], stop: Sequence[str] | None = None,
                          run_manager: Any = None, **kwargs: Any) -> Any:
                payload = [
                    {"role": _message_role(message), "content": _message_content(message)}
                    for message in messages
                ]
                text = self.client.chat(payload, temperature=0.2, max_tokens=4096)
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content=str(text)))])

            def bind_tools(self, tools: Sequence[Any], *, tool_choice: str | None = None,
                           **kwargs: Any) -> Any:
                # Tool calls are normalized by InternAgentAdapter.  Returning
                # the model keeps DeepAgents internals out of the product contract.
                return self

        return _InternChatModel(client=args[0], model_id=kwargs.get("model_id", "intern-s2"))


class DeepAgentsAdapter:
    """Use DeepAgents behind the product AgentAdapter boundary."""

    def __init__(
        self,
        client: Any,
        *,
        tools: Sequence[Callable[..., Any]] = (),
        system_prompt: str = "Solve the math problem and return a concise answer.",
        model_id: str = "intern-s2",
    ) -> None:
        try:
            from deepagents import create_deep_agent
        except ImportError as exc:  # pragma: no cover - product dependency boundary
            raise AdapterError("showcase_dependency_missing", "deepagents") from exc
        self._agent = create_deep_agent(
            model=InternChatModel(client, model_id=model_id),
            tools=list(tools),
            system_prompt=system_prompt,
        )

    def run(self, request: RunRequest) -> AgentResult:
        """Invoke DeepAgents and convert its final message into a product result."""

        try:
            result = self._agent.invoke({"messages": [{"role": "user", "content": request.problem}]})
        except Exception as exc:  # noqa: BLE001 - framework details stay behind adapter
            raise AdapterError("deepagents_error", type(exc).__name__) from exc
        text = _extract_agent_text(result)
        if not text:
            raise AdapterError("empty_agent_response")
        return AgentResult(final_response=text, summary="deepagents role adapter")


def _normalize_message(message: Mapping[str, Any]) -> dict[str, Any]:
    role = message.get("role")
    content = message.get("content")
    if not isinstance(role, str) or not isinstance(content, (str, list, tuple)):
        raise AdapterError("message_invalid")
    return {"role": role, "content": content}


def _extract_response(raw: Any) -> tuple[str, dict[str, Any]]:
    if isinstance(raw, str):
        return raw, {}
    if isinstance(raw, Mapping):
        content = raw.get("content", raw.get("text", ""))
        usage = raw.get("usage") if isinstance(raw.get("usage"), Mapping) else {}
        return str(content), dict(usage)
    return str(raw), {}


def _parse_tool_requests(text: str) -> list[ToolRequest]:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.IGNORECASE)
    try:
        payload = json.loads(candidate)
    except (TypeError, ValueError):
        return []
    if not isinstance(payload, Mapping):
        return []
    raw_calls = payload.get("tool_calls")
    if raw_calls is None and payload.get("tool_call") is not None:
        raw_calls = [payload.get("tool_call")]
    if not isinstance(raw_calls, Sequence) or isinstance(raw_calls, (str, bytes)):
        return []
    requests: list[ToolRequest] = []
    for call in raw_calls:
        if not isinstance(call, Mapping) or not isinstance(call.get("name"), str):
            continue
        arguments = call.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except (TypeError, ValueError):
                arguments = {}
        if not isinstance(arguments, Mapping):
            arguments = {}
        requests.append(ToolRequest(name=call["name"], arguments=dict(arguments)))
    return requests


def _accepts_keyword(function: Callable[..., Any], name: str) -> bool:
    try:
        import inspect

        parameters = inspect.signature(function).parameters
        return name in parameters or any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
        )
    except (TypeError, ValueError):
        return False


def _message_role(message: Any) -> str:
    role = getattr(message, "type", None)
    return {"human": "user", "ai": "assistant", "system": "system", "tool": "tool"}.get(
        role, "user"
    )


def _message_content(message: Any) -> Any:
    content = getattr(message, "content", "")
    if isinstance(content, (str, list, tuple)):
        return content
    return str(content)


def _extract_agent_text(result: Any) -> str:
    if isinstance(result, Mapping):
        direct = result.get("final_response")
        if isinstance(direct, str):
            return direct
        messages = result.get("messages")
        if isinstance(messages, Sequence):
            for message in reversed(messages):
                content = _message_content(message)
                if isinstance(content, str) and content.strip():
                    return content
    return ""


__all__ = [
    "AdapterError",
    "DeepAgentsAdapter",
    "InternAgentAdapter",
    "InternChatModel",
    "InternModelAdapter",
    "ModelResponse",
    "ToolRequest",
]
