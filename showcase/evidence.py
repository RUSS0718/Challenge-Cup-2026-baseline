"""JSON Evidence Pack export with product trace redaction."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from .verification import VerificationResult

_SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "credential",
    "hidden_answer",
    "image",
    "image_bytes",
    "image_base64",
    "full_image",
    "full_image_bytes",
    "full_image_base64",
    "password",
    "prompt",
    "secret",
    "token",
}


class EvidencePackExporter:
    """Export observable summaries while excluding sensitive request bodies."""

    version = "evidence-v0.1"

    def export(
        self,
        snapshot: Mapping[str, Any],
        *,
        events: Sequence[Mapping[str, Any]] = (),
        tool_results: Sequence[Mapping[str, Any]] = (),
        verification: VerificationResult | Mapping[str, Any] | None = None,
        artifacts: Sequence[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        """Return a JSON-compatible, redacted Evidence Pack."""

        verification_data = _verification_dict(verification)
        pack = {
            "version": self.version,
            "exported_at": datetime.now(UTC).isoformat(),
            "run": {
                "run_id": snapshot.get("run_id"),
                "profile": snapshot.get("profile"),
                "status": snapshot.get("status"),
                "stage": snapshot.get("stage"),
                "input_ref": snapshot.get("input_ref"),
                "asset_refs": snapshot.get("asset_refs", []),
                "final_response": snapshot.get("final_response"),
                "error": snapshot.get("error"),
            },
            "timeline": [_event_summary(event, index) for index, event in enumerate(events, 1)],
            "agent": {"summary": snapshot.get("agent_summary", "")},
            "tools": [_tool_summary(result) for result in tool_results],
            "verification": verification_data,
            "artifacts": [_redact(artifact) for artifact in artifacts],
            "feature_status": {
                "execution": "implemented",
                "python_math": "experimental",
                "multimodal": "implemented" if snapshot.get("asset_refs") else "planned",
                "verification": "implemented",
            },
        }
        return _redact(pack)

    def to_json(self, pack: Mapping[str, Any]) -> str:
        """Serialize an Evidence Pack with stable UTF-8 JSON."""

        return json.dumps(pack, ensure_ascii=False, sort_keys=True, indent=2)


def _verification_dict(value: VerificationResult | Mapping[str, Any] | None) -> dict[str, Any]:
    if isinstance(value, VerificationResult):
        return {
            "status": value.status,
            "findings": list(value.findings),
            "checker": value.checker,
        }
    if isinstance(value, Mapping):
        return dict(value)
    return {"status": "unknown", "findings": ["verification_not_run"]}


def _event_summary(event: Mapping[str, Any], index: int) -> dict[str, Any]:
    return {
        "evidence_id": f"event_{index}",
        "type": event.get("type", "unknown"),
        "sequence": event.get("sequence", index),
        "status": event.get("status"),
        "stage": event.get("stage"),
        "summary": event.get("summary", ""),
        "error_category": event.get("error_category"),
    }


def _tool_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "evidence_id": result.get("evidence_id", result.get("name", "tool")),
        "name": result.get("name"),
        "status": result.get("status"),
        "duration_seconds": result.get("duration_seconds"),
        "parameter_summary": result.get("parameter_summary", ""),
        "result_summary": result.get("result_summary", ""),
        "error_category": result.get("error_category"),
    }


def _redact(value: Any, *, key: str | None = None) -> Any:
    if key is not None and key.lower() in _SENSITIVE_KEYS:
        return "[redacted]"
    if isinstance(value, Mapping):
        return {str(name): _redact(item, key=str(name)) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


__all__ = ["EvidencePackExporter"]
