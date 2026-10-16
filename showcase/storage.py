"""Small SQLite repository for the product-side Run contract."""

from __future__ import annotations

import copy
import json
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "credential",
    "password",
    "prompt",
    "secret",
    "token",
}


class PersistenceError(RuntimeError):
    """Sanitized storage error exposed by the product service."""

    category = "persistence_error"

    def __init__(self, operation: str) -> None:
        super().__init__(self.category)
        self.operation = operation


class SQLiteStore:
    """Persist Run snapshots, append-only events, checkpoints, and artifacts."""

    def __init__(self, database_path: str | Path = ":memory:") -> None:
        self.database_path = str(database_path)
        try:
            self._connection = sqlite3.connect(self.database_path, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    snapshot_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, sequence),
                    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS checkpoints (
                    run_id TEXT PRIMARY KEY,
                    checkpoint_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    run_id TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    artifact_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, artifact_id),
                    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
                );
                """
            )
            self._connection.commit()
        except sqlite3.Error as exc:
            raise PersistenceError("open") from exc

    def save_run(self, snapshot: Mapping[str, Any]) -> None:
        """Insert or replace one normalized Run snapshot."""

        run_id = snapshot.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise PersistenceError("save_run")
        payload = _json(snapshot, "save_run")
        created_at = str(snapshot.get("created_at") or _utc_now())
        updated_at = str(snapshot.get("updated_at") or created_at)
        try:
            self._connection.execute(
                """
                INSERT INTO runs(run_id, snapshot_json, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    snapshot_json=excluded.snapshot_json,
                    updated_at=excluded.updated_at
                """,
                (run_id, payload, created_at, updated_at),
            )
            self._connection.commit()
        except sqlite3.Error as exc:
            raise PersistenceError("save_run") from exc

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Read one Run snapshot, or return ``None`` when it is absent."""

        try:
            row = self._connection.execute(
                "SELECT snapshot_json FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            raise PersistenceError("get_run") from exc
        return None if row is None else _loads(row["snapshot_json"], "get_run")

    def append_event(self, run_id: str, event: Mapping[str, Any]) -> dict[str, Any]:
        """Append a redacted event with a monotonic per-Run sequence number."""

        safe_event = _redact(event)
        safe_event.setdefault("created_at", _utc_now())
        try:
            row = self._connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) AS last_sequence FROM events WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise PersistenceError("append_event")
            sequence = int(row["last_sequence"]) + 1
            safe_event["sequence"] = sequence
            safe_event["run_id"] = run_id
            self._connection.execute(
                "INSERT INTO events(run_id, sequence, event_json, created_at) VALUES (?, ?, ?, ?)",
                (run_id, sequence, _json(safe_event, "append_event"), safe_event["created_at"]),
            )
            self._connection.commit()
        except PersistenceError:
            raise
        except sqlite3.Error as exc:
            raise PersistenceError("append_event") from exc
        return copy.deepcopy(safe_event)

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        """Return append-only events in sequence order."""

        try:
            rows = self._connection.execute(
                "SELECT event_json FROM events WHERE run_id = ? ORDER BY sequence", (run_id,)
            ).fetchall()
        except sqlite3.Error as exc:
            raise PersistenceError("get_events") from exc
        return [_loads(row["event_json"], "get_events") for row in rows]

    def save_checkpoint(self, run_id: str, checkpoint: Mapping[str, Any]) -> None:
        """Replace the latest checkpoint while retaining all events."""

        safe_checkpoint = _redact(checkpoint)
        try:
            self._connection.execute(
                """
                INSERT INTO checkpoints(run_id, checkpoint_json, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    checkpoint_json=excluded.checkpoint_json,
                    created_at=excluded.created_at
                """,
                (run_id, _json(safe_checkpoint, "save_checkpoint"), _utc_now()),
            )
            self._connection.commit()
        except sqlite3.Error as exc:
            raise PersistenceError("save_checkpoint") from exc

    def get_checkpoint(self, run_id: str) -> dict[str, Any] | None:
        """Read the latest checkpoint for a Run."""

        try:
            row = self._connection.execute(
                "SELECT checkpoint_json FROM checkpoints WHERE run_id = ?", (run_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            raise PersistenceError("get_checkpoint") from exc
        return None if row is None else _loads(row["checkpoint_json"], "get_checkpoint")

    def save_artifact(self, run_id: str, artifact_id: str, artifact: Mapping[str, Any]) -> None:
        """Store a redacted artifact index entry without the binary payload."""

        try:
            self._connection.execute(
                """
                INSERT INTO artifacts(run_id, artifact_id, artifact_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id, artifact_id) DO UPDATE SET artifact_json=excluded.artifact_json
                """,
                (run_id, artifact_id, _json(_redact(artifact), "save_artifact"), _utc_now()),
            )
            self._connection.commit()
        except sqlite3.Error as exc:
            raise PersistenceError("save_artifact") from exc

    def get_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        """Return artifact index entries in insertion order."""

        try:
            rows = self._connection.execute(
                "SELECT artifact_json FROM artifacts WHERE run_id = ? ORDER BY created_at",
                (run_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise PersistenceError("get_artifacts") from exc
        return [_loads(row["artifact_json"], "get_artifacts") for row in rows]

    def close(self) -> None:
        """Close the SQLite connection."""

        self._connection.close()

    def __enter__(self) -> SQLiteStore:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


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


def _json(value: Any, operation: str) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise PersistenceError(operation) from exc


def _loads(value: str, operation: str) -> dict[str, Any]:
    try:
        result = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise PersistenceError(operation) from exc
    if not isinstance(result, dict):
        raise PersistenceError(operation)
    return result


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
