"""Deterministic replay evidence used when live credentials are unavailable."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .evidence import EvidencePackExporter


class ReplayValidationError(ValueError):
    """Raised when a replay artifact is missing its public contract."""

    category = "replay_invalid"


def load_replay(path: str | Path) -> dict[str, Any]:
    """Load one redacted replay pack and mark it explicitly as replay."""

    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReplayValidationError("replay_read_failed") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("run"), dict):
        raise ReplayValidationError("replay_contract_invalid")
    result = dict(payload)
    result["run_mode"] = "replay"
    result.setdefault("feature_status", {})
    result["feature_status"].setdefault("replay", "implemented")
    return result


def write_sample_replay(path: str | Path) -> dict[str, Any]:
    """Write a small failure/recovery replay with no raw prompt or image."""

    exporter = EvidencePackExporter()
    snapshot = {
        "run_id": "run_replay_v01",
        "profile": "showcase_mvp",
        "status": "COMPLETED",
        "stage": "completed",
        "input_ref": {"kind": "text", "sha256": "replay-only", "length": 24},
        "asset_refs": [],
        "final_response": "回放结果：2",
        "error": None,
    }
    events = [
        {"sequence": 1, "type": "run_received", "status": "RECEIVED", "stage": "planning"},
        {"sequence": 2, "type": "tool_completed", "status": "timeout", "stage": "running", "error_category": "python_timeout", "summary": "实验工具超时"},
        {"sequence": 3, "type": "resume_requested", "status": "RESUMED", "stage": "solving", "summary": "保留原失败事件后恢复"},
        {"sequence": 4, "type": "run_completed", "status": "COMPLETED", "stage": "completed", "summary": "回放完成"},
    ]
    pack = exporter.export(
        snapshot,
        events=events,
        tool_results=[
            {
                "name": "python_math",
                "status": "timeout",
                "parameter_summary": '{"code":{"type":"str","length":12}}',
                "result_summary": "python_timeout",
                "error_category": "python_timeout",
            }
        ],
        verification={"status": "unknown", "findings": ["replay_evidence"]},
    )
    pack["run_mode"] = "replay"
    pack["feature_status"].update(
        {"live_model": "unavailable", "python_math": "experimental", "recovery": "implemented"}
    )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(pack, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return pack


__all__ = ["ReplayValidationError", "load_replay", "write_sample_replay"]
