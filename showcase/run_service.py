"""In-memory Run application service for the ``showcase_mvp`` profile.

This first product slice owns the public Run contract and uses a deterministic
fake Agent. Persistence, graph execution, tools, and live model adapters are
deliberately left to later slices behind the same adapter boundary.
"""

from __future__ import annotations

import copy
import hashlib
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from .profile import SHOWCASE_PROFILE, ensure_showcase_profile
from .storage import SQLiteStore

MAX_PROBLEM_CHARS = 10_000
MAX_ASSET_REFS = 32


class RunValidationError(ValueError):
    """Raised when a request cannot enter the Agent boundary."""

    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


class RunNotFoundError(KeyError):
    """Raised when a caller requests a Run that this service does not own."""

    category = "run_not_found"

    def __init__(self, run_id: str) -> None:
        super().__init__(f"{self.category}: {run_id}")
        self.run_id = run_id


@dataclass(frozen=True)
class RunRequest:
    """Normalized input passed to a product Agent adapter."""

    problem: str
    profile: str = SHOWCASE_PROFILE
    metadata: Mapping[str, Any] = field(default_factory=dict)
    asset_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentResult:
    """Adapter result normalized before it becomes a public Run snapshot."""

    final_response: str
    summary: str = ""


class AgentAdapter(Protocol):
    """Minimal seam used by the Run application service."""

    def run(self, request: RunRequest) -> AgentResult | Mapping[str, Any]:
        """Produce one deterministic or live result for a validated request."""


class FakeAgentAdapter:
    """Credential-free adapter used by the first vertical slice and tests."""

    def run(self, request: RunRequest) -> AgentResult:
        """Return an observable result without calling a provider or tool."""

        return AgentResult(
            final_response="Fake Agent completed a deterministic showcase run.",
            summary=f"fake adapter; input length={len(request.problem)}",
        )


class RunService:
    """Create and query product Runs without importing official runtime code."""

    def __init__(
        self,
        agent: AgentAdapter | None = None,
        *,
        profile: str = SHOWCASE_PROFILE,
        database_path: str | Any = ":memory:",
    ) -> None:
        ensure_showcase_profile(profile)
        self.profile = profile
        self._agent = agent or FakeAgentAdapter()
        self._store = SQLiteStore(database_path)

    def create_run(self, request: RunRequest | Mapping[str, Any]) -> dict[str, Any]:
        """Validate, execute once through the Agent seam, and return a snapshot."""

        normalized = self._normalize_request(request)
        now = _utc_now()
        run_id = f"run_{uuid.uuid4().hex}"
        snapshot = {
            "run_id": run_id,
            "profile": self.profile,
            "status": "RUNNING",
            "stage": "solving",
            "input_ref": _input_ref(normalized.problem),
            "asset_refs": list(normalized.asset_refs),
            "result": None,
            "final_response": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
        }
        self._store.save_run(snapshot)
        self._store.append_event(
            run_id,
            {"type": "run_received", "status": snapshot["status"], "stage": snapshot["stage"]},
        )
        self._store.save_checkpoint(run_id, snapshot)

        try:
            result = self._normalize_result(self._agent.run(normalized))
        except Exception as exc:  # noqa: BLE001 - adapter errors become safe Run state
            snapshot.update(
                {
                    "status": "FAILED",
                    "stage": "failed",
                    "error": {"category": "agent_failure", "summary": type(exc).__name__},
                    "updated_at": _utc_now(),
                }
            )
            self._store.append_event(
                run_id,
                {
                    "type": "run_failed",
                    "status": snapshot["status"],
                    "stage": snapshot["stage"],
                    "error": snapshot["error"],
                },
            )
        else:
            snapshot.update(
                {
                    "status": "COMPLETED",
                    "stage": "synthesis",
                    "result": {
                        "final_response": result.final_response,
                        "summary": result.summary,
                    },
                    "final_response": result.final_response,
                    "updated_at": _utc_now(),
                }
            )
            self._store.append_event(
                run_id,
                {
                    "type": "agent_completed",
                    "status": snapshot["status"],
                    "stage": snapshot["stage"],
                    "summary": result.summary,
                },
            )
            self._store.append_event(
                run_id,
                {"type": "run_completed", "status": snapshot["status"], "stage": snapshot["stage"]},
            )

        self._store.save_run(snapshot)
        self._store.save_checkpoint(run_id, snapshot)
        return self._copy_snapshot(snapshot)

    def get_run(self, run_id: str) -> dict[str, Any]:
        """Return an isolated snapshot so callers cannot mutate service state."""

        snapshot = self._store.get_run(run_id)
        if snapshot is None:
            raise RunNotFoundError(run_id)
        return self._copy_snapshot(snapshot)

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        """Return append-only events for a Run."""

        self._require_run(run_id)
        return copy.deepcopy(self._store.get_events(run_id))

    def append_event(self, run_id: str, event: Mapping[str, Any]) -> dict[str, Any]:
        """Append a redacted observable event without rewriting Run history."""

        self._require_run(run_id)
        return self._store.append_event(run_id, event)

    def get_checkpoint(self, run_id: str) -> dict[str, Any] | None:
        """Read the most recent recoverable checkpoint."""

        self._require_run(run_id)
        return self._store.get_checkpoint(run_id)

    def save_checkpoint(self, run_id: str, checkpoint: Mapping[str, Any]) -> None:
        """Replace the latest checkpoint while retaining previous events."""

        self._require_run(run_id)
        self._store.save_checkpoint(run_id, checkpoint)

    def close(self) -> None:
        """Release the product persistence connection."""

        self._store.close()

    def _require_run(self, run_id: str) -> dict[str, Any]:
        snapshot = self._store.get_run(run_id)
        if snapshot is None:
            raise RunNotFoundError(run_id)
        return snapshot

    def health(self) -> dict[str, str]:
        """Return a credential-free service health response."""

        return {"status": "ok", "service": "showcase_run", "profile": self.profile}

    def _normalize_request(self, request: RunRequest | Mapping[str, Any]) -> RunRequest:
        if isinstance(request, RunRequest):
            candidate: Mapping[str, Any] = request.__dict__
        elif isinstance(request, Mapping):
            candidate = request
        else:
            raise RunValidationError("request_must_be_object")

        problem = candidate.get("problem")
        if not isinstance(problem, str):
            raise RunValidationError("problem_must_be_string")
        problem = problem.strip()
        if not problem:
            raise RunValidationError("problem_must_be_non_empty")
        if len(problem) > MAX_PROBLEM_CHARS:
            raise RunValidationError("problem_too_large")

        profile = candidate.get("profile", self.profile)
        if profile != self.profile:
            raise RunValidationError("profile_must_be_showcase_mvp")

        metadata = candidate.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise RunValidationError("metadata_must_be_object")

        raw_asset_refs = candidate.get("asset_refs", ())
        if isinstance(raw_asset_refs, (str, bytes)) or not isinstance(raw_asset_refs, Sequence):
            raise RunValidationError("asset_refs_must_be_list")
        asset_refs = tuple(raw_asset_refs)
        if len(asset_refs) > MAX_ASSET_REFS:
            raise RunValidationError("too_many_asset_refs")
        if any(not isinstance(asset_ref, str) or not asset_ref.strip() for asset_ref in asset_refs):
            raise RunValidationError("asset_ref_must_be_non_empty_string")

        return RunRequest(
            problem=problem,
            profile=self.profile,
            metadata=dict(metadata),
            asset_refs=asset_refs,
        )

    @staticmethod
    def _normalize_result(result: AgentResult | Mapping[str, Any]) -> AgentResult:
        if isinstance(result, AgentResult):
            normalized = result
        elif isinstance(result, Mapping):
            final_response = result.get("final_response")
            summary = result.get("summary", "")
            if not isinstance(final_response, str) or not final_response.strip():
                raise ValueError("agent_result_missing_final_response")
            normalized = AgentResult(final_response=final_response, summary=str(summary))
        else:
            raise TypeError("agent_result_must_be_object")

        if not normalized.final_response.strip():
            raise ValueError("agent_result_missing_final_response")
        return normalized

    @staticmethod
    def _copy_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(snapshot)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _input_ref(problem: str) -> dict[str, Any]:
    digest = hashlib.sha256(problem.encode("utf-8")).hexdigest()
    return {"kind": "text", "sha256": digest, "length": len(problem)}
