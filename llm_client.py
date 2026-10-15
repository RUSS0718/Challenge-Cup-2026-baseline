"""Local Intern-S2 client with request-scoped reasoning and safe diagnostics."""

import hashlib
import json
import os
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import requests

DEFAULT_API_BASE = "https://chat.intern-ai.org.cn/api/v1/chat/completions"
# The provider's API identifier for the current Intern-S2 model.
DEFAULT_MODEL = "intern-s2"
ReasoningMode = Literal["inherit", "off", "on"]


def _load_local_env() -> None:
    """Load simple KEY=VALUE settings from the repository .env, overriding Windows values."""
    env_path = Path(__file__).with_name(".env")
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if name:
            os.environ[name] = value


_load_local_env()


class ChatClientError(RuntimeError):
    """A sanitized failure category suitable for trace and local reports."""

    def __init__(self, category: str, detail: str | None = None) -> None:
        super().__init__(category)
        self.category = category
        self.detail = detail


class InternChatClient:
    """Small OpenAI-compatible chat client for the competition sample."""

    def __init__(
        self,
        timeout: int | None = None,
        retry: int | None = None,
        thinking_mode: bool | None = None,
    ) -> None:
        raw_api_key = os.environ.get("INTERN_API_KEY")
        if not raw_api_key:
            raise ChatClientError("configuration")
        self.authorization = (
            raw_api_key if raw_api_key.startswith("Bearer ") else f"Bearer {raw_api_key}"
        )
        self.api_base = os.environ.get("INTERN_API_BASE", DEFAULT_API_BASE)
        self.model = os.environ.get("INTERN_MODEL", DEFAULT_MODEL)
        # Explicit kwarg wins over the env switch so experiments can pin the
        # thinking switch per arm without touching process env.
        self.thinking_mode = (
            thinking_mode
            if thinking_mode is not None
            else _optional_bool_env("INTERN_THINKING_MODE")
        )
        self.timeout = (
            timeout if timeout is not None else _positive_int_env("INTERN_TIMEOUT_SECONDS", 30)
        )
        self.retry = retry if retry is not None else _positive_int_env("INTERN_RETRY_COUNT", 1)
        # P0.1: per-call finish_reason log (local diagnostic only; the official
        # client keeps its own counters).  Appended in call order for serial runs.
        self.finish_reasons: list[str] = []
        # 13.2 A/B diagnostics: per-call completion token count and raw content,
        # so the evaluator can measure thinking-leak rate / marker rate / output
        # tokens without re-requesting.  Local-only; the official client is
        # untouched and never sees these lists.
        self.completion_tokens: list[int] = []
        self.raw_contents: list[str] = []
        self.response_metadata: list[dict[str, Any]] = []
        self.last_response_metadata: dict[str, Any] | None = None
        # 13.2 token A/B: per-call wall-clock latency (aligned with the lists above,
        # appended once per successful chat call so before/after slicing works).
        self.latencies: list[float] = []
        # Sanitized per-attempt metadata for local diagnosis; never stores
        # authorization headers, prompts, or response content.
        self.request_diagnostics: list[dict[str, Any]] = []
        self._logical_call_count = 0
        self._request_sequence = 0
        self.last_failure_category: str | None = None
        self.last_failure_type: str | None = None

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 4096,
        *,
        reasoning_mode: ReasoningMode = "inherit",
        thinking_mode: bool | None = None,
        timeout_seconds: int | None = None,
    ) -> str:
        """Send a request; explicit reasoning_mode wins over thinking_mode and defaults."""
        effective_timeout = self.timeout if timeout_seconds is None else int(timeout_seconds)
        if effective_timeout <= 0:
            raise ValueError("timeout_seconds_must_be_positive")
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        effective_thinking_mode = self._resolve_reasoning_mode(reasoning_mode)
        if reasoning_mode == "inherit" and thinking_mode is not None:
            effective_thinking_mode = thinking_mode
        if effective_thinking_mode is not None:
            payload["thinking_mode"] = effective_thinking_mode
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.authorization,
        }

        message_bytes = json.dumps(
            messages, ensure_ascii=False, sort_keys=True, default=str
        ).encode("utf-8")
        logical_call_index = self._logical_call_count
        self._logical_call_count += 1
        request_metadata = {
            "logical_call_index": logical_call_index,
            "request_model_id": self.model,
            "api_host": urlparse(self.api_base).netloc,
            "reasoning_mode": reasoning_mode,
            "thinking_mode": effective_thinking_mode,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout_seconds": effective_timeout,
            "attempts_configured": self.retry,
            "message_count": len(messages),
            "message_roles": [str(message.get("role", "")) for message in messages],
            "messages_sha256": hashlib.sha256(message_bytes).hexdigest(),
        }
        last_category = "request"
        started = time.perf_counter()
        self.last_response_metadata = None
        for attempt in range(self.retry):
            attempt_started = time.perf_counter()
            request_event: dict[str, Any] = {
                **request_metadata,
                "request_sequence": self._request_sequence,
                "attempt_index": attempt + 1,
                "started_at_utc": datetime.now(UTC).isoformat(),
                "status": "pending",
            }
            response = None
            failure: BaseException | None = None
            try:
                response = requests.post(
                    self.api_base,
                    headers=headers,
                    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    timeout=effective_timeout,
                )
                response.raise_for_status()
                data = response.json()
                choice = data["choices"][0]
                finish_reason = choice.get("finish_reason") or ""
                request_event.update(
                    status="success",
                    http_status=getattr(response, "status_code", None),
                    response_id=data.get("id") if isinstance(data.get("id"), str) else None,
                    response_model_id=(
                        data.get("model") if isinstance(data.get("model"), str) else None
                    ),
                    finish_reason=finish_reason,
                )
                self.finish_reasons.append(finish_reason)
                usage = data.get("usage") or {}
                try:
                    completion_tokens = int(usage.get("completion_tokens") or 0)
                except (TypeError, ValueError):
                    completion_tokens = 0
                self.completion_tokens.append(completion_tokens)
                for usage_field in ("prompt_tokens", "total_tokens"):
                    try:
                        request_event[usage_field] = int(usage.get(usage_field) or 0)
                    except (TypeError, ValueError):
                        request_event[usage_field] = None
                request_event["completion_tokens"] = completion_tokens
                message = choice["message"]
                content = message["content"]
                reasoning_content = (
                    message.get("reasoning_content") if isinstance(message, Mapping) else None
                )
                response_metadata = {
                    "has_reasoning_content": bool(
                        isinstance(reasoning_content, str) and reasoning_content
                    ),
                    "reasoning_content_chars": (
                        len(reasoning_content) if isinstance(reasoning_content, str) else 0
                    ),
                    "content_chars": len(content) if isinstance(content, str) else 0,
                    "finish_reason": finish_reason,
                    "completion_tokens": completion_tokens,
                }
                self.response_metadata.append(response_metadata)
                self.last_response_metadata = dict(response_metadata)
                self.raw_contents.append(content if isinstance(content, str) else "")
                request_event["response_content_chars"] = (
                    len(content) if isinstance(content, str) else None
                )
                request_event.update(
                    {
                        "has_reasoning_content": response_metadata["has_reasoning_content"],
                        "reasoning_content_chars": response_metadata["reasoning_content_chars"],
                        "content_chars": response_metadata["content_chars"],
                    }
                )
                self.latencies.append(time.perf_counter() - started)
                return content
            except requests.Timeout as exc:
                last_category = "timeout"
                failure = exc
                self._record_failure(last_category, exc)
            except requests.exceptions.ProxyError as exc:
                last_category = "proxy"
                failure = exc
                self._record_failure(last_category, exc)
            except requests.exceptions.SSLError as exc:
                last_category = "tls"
                failure = exc
                self._record_failure(last_category, exc)
            except requests.ConnectionError as exc:
                last_category = "connectivity"
                failure = exc
                self._record_failure(last_category, exc)
            except requests.HTTPError as exc:
                last_category = "http_status"
                failure = exc
                self._record_failure(last_category, exc)
            except (KeyError, TypeError, ValueError) as exc:
                last_category = "invalid_response"
                failure = exc
                self._record_failure(last_category, exc)
            except requests.RequestException as exc:
                last_category = "request"
                failure = exc
                self._record_failure(last_category, exc)
            except Exception as exc:
                failure = exc
                last_category = "client_exception"
                self._record_failure(last_category, exc)
                raise
            finally:
                request_event["duration_seconds"] = round(time.perf_counter() - attempt_started, 3)
                if failure is not None:
                    failure_response = (
                        response if response is not None else getattr(failure, "response", None)
                    )
                    request_event.update(
                        status="error",
                        error_category=last_category,
                        error_type=type(failure).__name__,
                        http_status=(
                            getattr(failure_response, "status_code", None)
                            if failure_response is not None
                            else None
                        ),
                    )
                self.request_diagnostics.append(request_event)
                self._request_sequence += 1
            if attempt + 1 < self.retry:
                time.sleep(2**attempt)

        raise ChatClientError(last_category, self.last_failure_type)

    def _resolve_reasoning_mode(self, reasoning_mode: ReasoningMode) -> bool | None:
        """Resolve an explicit request mode against the unchanged client default."""
        if reasoning_mode == "off":
            return False
        if reasoning_mode == "on":
            return True
        if reasoning_mode == "inherit":
            return self.thinking_mode
        raise ValueError("invalid_reasoning_mode")

    def diagnostic_snapshot(self) -> dict[str, str | None]:
        """Return safe local diagnostics; never includes credentials or prompts."""
        parsed = urlparse(self.api_base)
        return {
            "model": self.model,
            "thinking_mode": self.thinking_mode,
            "api_host": parsed.netloc,
            "last_failure_category": self.last_failure_category,
            "last_failure_type": self.last_failure_type,
        }

    def _record_failure(self, category: str, exc: BaseException) -> None:
        self.last_failure_category = category
        if isinstance(exc, requests.HTTPError) and getattr(exc, "response", None) is not None:
            status = getattr(exc.response, "status_code", None)
            self.last_failure_type = f"HTTPError:{status}" if status is not None else "HTTPError"
        else:
            self.last_failure_type = type(exc).__name__


def _positive_int_env(name: str, default: int) -> int:
    """Read a bounded local diagnostic setting without exposing environment values."""
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _optional_bool_env(name: str) -> bool | None:
    value = os.environ.get(name)
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None
