"""Shared redaction policy for product traces, tools, and Evidence Packs."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

MAX_SUMMARY_CHARS = 1_000

_SENSITIVE_KEY_PARTS = {
    "apikey",
    "authorization",
    "credential",
    "password",
    "prompt",
    "secret",
    "token",
    "hiddenanswer",
    "imagebytes",
    "imagebase64",
    "fullimage",
    "fullimagebytes",
    "fullimagebase64",
    "personaldata",
    "pii",
}
_SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?i)(api[_-]?key|authorization|credential|password|secret|token|"
    r"hidden[_-]?answer|full[_-]?prompt|full[_-]?image(?:[_-]?(?:bytes|base64))?)"
    r"\s*[:=]\s*([^,;\s]+)"
)


def _normalized_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def is_sensitive_key(key: str) -> bool:
    """Return whether a field name identifies a value that must not be stored."""

    normalized = _normalized_key(key)
    return normalized in _SENSITIVE_KEY_PARTS or any(
        normalized.startswith(prefix)
        for prefix in ("fullimage", "hiddenanswer", "fullprompt")
    )


def redact_text(value: str) -> str:
    """Remove common key=value leaks from human-readable summaries."""

    return _SENSITIVE_TEXT_PATTERN.sub(lambda match: f"{match.group(1)}=[redacted]", value)


def redact(value: Any, *, key: str | None = None) -> Any:
    """Recursively redact sensitive fields and string-level key/value leaks."""

    if key is not None and is_sensitive_key(key):
        return "[redacted]"
    if isinstance(value, Mapping):
        return {str(name): redact(item, key=str(name)) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return redact_text(str(value))


def summarize_parameters(arguments: Mapping[str, Any]) -> str:
    """Describe argument shape without persisting values, prompts, or code."""

    summary: dict[str, Any] = {}
    for name, value in sorted(arguments.items(), key=lambda item: str(item[0])):
        field_name = str(name)
        if is_sensitive_key(field_name):
            summary[field_name] = "[redacted]"
            continue
        item: dict[str, Any] = {"type": type(value).__name__}
        if isinstance(value, (str, bytes, list, tuple, dict)):
            item["length"] = len(value)
        summary[field_name] = item
    return json.dumps(summary, ensure_ascii=False, sort_keys=True)[:MAX_SUMMARY_CHARS]


def sensitive_markers(value: Any) -> list[str]:
    """Find marker names in serialized release artifacts."""

    text = json.dumps(value, ensure_ascii=False, default=str).lower()
    markers = (
        "api_key",
        "apikey",
        "authorization",
        "credential",
        "password",
        "secret",
        "token",
        "hidden_answer",
        "full_prompt",
        "image_bytes",
        "image_base64",
        "full_image",
    )
    return [marker for marker in markers if marker in text]


__all__ = [
    "is_sensitive_key",
    "redact",
    "redact_text",
    "sensitive_markers",
    "summarize_parameters",
]
