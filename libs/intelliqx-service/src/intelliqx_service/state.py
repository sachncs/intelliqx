"""SQLite-backed run state store.

Stores run records in a single table; exposes enqueue/claim_next/
complete/cancel/get primitives. Concurrency is serialised with
``BEGIN IMMEDIATE`` to take the SQLite write lock, which closes
the TOCTOU window between the pending SELECT and the status
update. The store is single-process; multi-process deployments
need a real queue.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any


class RunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RunNotFoundError(KeyError):
    """Raised when a run id is not present in the store."""


class RunNotCancellableError(RuntimeError):
    """Raised when a run is in a terminal state and cannot be cancelled."""


def _isoformat(timestamp: float) -> str:
    """Return an ISO 8601 string for the given epoch seconds."""
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()


@dataclass
class RunRecord:
    """One row of the ``runs`` table, projected for the HTTP layer."""

    run_id: str
    agent_name: str
    tenant_id: str
    status: RunStatus
    input_payload: dict[str, Any]
    output: dict[str, Any] | None
    error: str | None
    attempts: int
    max_retries: int
    created_at: float
    updated_at: float
    duration_ms: int

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable view with ISO 8601 timestamps."""
        return {
            "run_id": self.run_id,
            "agent_name": self.agent_name,
            "tenant_id": self.tenant_id,
            "status": self.status.value,
            "input": self.input_payload,
            "output": self.output,
            "error": self.error,
            "attempts": self.attempts,
            "max_retries": self.max_retries,
            "created_at": _isoformat(self.created_at),
            "updated_at": _isoformat(self.updated_at),
            "duration_ms": self.duration_ms,
        }


class StateStore:
    """Thread-safe SQLite run queue + status table.

    The store exposes the same minimal surface the worker needs:
    enqueue, claim_next, complete, requeue, cancel, get, ping,
    close. Concurrency is handled with a process-wide
    ``threading.Lock`` and ``BEGIN IMMEDIATE`` on writes so the
    pending SELECT and the RUNNING update run inside a single
    write transaction.
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS runs (
        run_id        TEXT PRIMARY KEY,
        agent_name    TEXT NOT NULL,
        tenant_id     TEXT NOT NULL,
        status       TEXT NOT NULL,
        input_json    TEXT NOT NULL,
        output_json   TEXT,
        error        TEXT,
        attempts     INTEGER NOT NULL DEFAULT 0,
        max_retries  INTEGER NOT NULL DEFAULT 1,
        created_at   REAL NOT NULL,
        updated_at   REAL NOT NULL,
        duration_ms  INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_runs_status_updated
        ON runs(status, updated_at);
    """

    def __init__(self, path: str | Path, *, run_ttl_seconds: int = 3600) -> None:
        self._path = str(path)
        self._is_memory = self._path == ":memory:"
        self._run_ttl_seconds = run_ttl_seconds
        self._conn = sqlite3.connect(  # type: ignore[call-overload]
            self._path, check_same_thread=False, uri=self._path if self._is_memory else None
        )
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._ensure_pragmas()
        self._conn.executescript(self.SCHEMA)
        self._conn.commit()

    def _ensure_pragmas(self) -> None:
        """Enable WAL and enforce foreign keys, raising on unsupported setups."""
        self._conn.execute("PRAGMA journal_mode=WAL")
        mode_row = self._conn.execute("PRAGMA journal_mode").fetchone()
        if mode_row is None or mode_row[0].lower() != "wal":
            raise RuntimeError(
                "SQLite must run in WAL journal mode; the platform refuses to "
                "fall back to a non-concurrent setup."
            )
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def ping(self) -> None:
        with self._lock:
            self._conn.execute("SELECT 1").fetchone()

    def enqueue(
        self,
        *,
        run_id: str,
        agent_name: str,
        tenant_id: str,
        input_payload: dict[str, Any],
        max_retries: int = 1,
    ) -> None:
        """Insert a PENDING row for the worker to pick up."""
        now = time.time()
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute(
                    "INSERT INTO runs(run_id, agent_name, tenant_id, status, "
                    "input_json, attempts, max_retries, created_at, updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        agent_name,
                        tenant_id,
                        RunStatus.PENDING.value,
                        json.dumps(input_payload),
                        0,
                        max_retries,
                        now,
                        now,
                    ),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def claim_next(self) -> tuple[str, str, dict[str, Any], str, int] | None:
        """Claim the oldest PENDING run and mark it RUNNING.

        Returns ``(run_id, agent, input_payload, tenant_id, next_attempt)``
        or ``None`` if no PENDING run is available. ``next_attempt`` is
        the new attempt count after the claim.
        """
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT rowid, run_id, agent_name, input_json, tenant_id, "
                    "attempts, max_retries "
                    "FROM runs WHERE status = ? "
                    "ORDER BY created_at ASC LIMIT 1",
                    (RunStatus.PENDING.value,),
                ).fetchone()
                if row is None:
                    self._conn.rollback()
                    return None
                attempts = int(row["attempts"]) + 1
                if attempts > int(row["max_retries"]):
                    self._conn.execute(
                        "UPDATE runs SET status = ?, updated_at = ? " "WHERE rowid = ?",
                        (RunStatus.FAILED.value, time.time(), row["rowid"]),
                    )
                    self._conn.commit()
                    return None
                self._conn.execute(
                    "UPDATE runs SET status = ?, attempts = ?, updated_at = ? " "WHERE rowid = ?",
                    (RunStatus.RUNNING.value, attempts, time.time(), row["rowid"]),
                )
                self._conn.commit()
                return (
                    row["run_id"],
                    row["agent_name"],
                    json.loads(row["input_json"]),
                    row["tenant_id"],
                    attempts,
                )
            except Exception:
                self._conn.rollback()
                raise

    def complete(
        self,
        run_id: str,
        status: RunStatus,
        output: dict[str, Any] | None = None,
        error: str | None = None,
        duration_ms: int = 0,
    ) -> None:
        """Persist the terminal state for a run."""
        now = time.time()
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute(
                    "UPDATE runs SET status = ?, output_json = ?, error = ?, "
                    "duration_ms = ?, updated_at = ? WHERE run_id = ?",
                    (
                        status.value,
                        json.dumps(output) if output is not None else None,
                        error,
                        duration_ms,
                        now,
                        run_id,
                    ),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def requeue(self, run_id: str, next_attempt: int) -> None:
        """Reset the run to PENDING and record the new attempt count."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute(
                    "UPDATE runs SET status = ?, attempts = ?, updated_at = ? " "WHERE run_id = ?",
                    (RunStatus.PENDING.value, next_attempt, time.time(), run_id),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def cancel(self, run_id: str) -> bool:
        """Cancel a PENDING or RUNNING run.

        Returns:
            True when the run was cancelled. False when the run does
            not exist or is already in a terminal state.
        """
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT status FROM runs WHERE run_id = ?", (run_id,)
                ).fetchone()
                if row is None or row["status"] not in {
                    RunStatus.PENDING.value,
                    RunStatus.RUNNING.value,
                }:
                    self._conn.rollback()
                    return False
                self._conn.execute(
                    "UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ?",
                    (RunStatus.CANCELLED.value, time.time(), run_id),
                )
                self._conn.commit()
                return True
            except Exception:
                self._conn.rollback()
                raise

    def get(self, run_id: str) -> RunRecord | None:
        """Return the current state of one run, or ``None`` if missing."""
        with self._lock:
            row = self._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                return None
            return _row_to_record(row)

    def close_expired(self, *, now: float | None = None) -> int:
        """Delete RUNNING rows whose last update is older than the TTL.

        Returns the number of rows deleted. This is the recovery path
        for runs that the worker never finished (e.g. process killed
        mid-invocation); they will not be retried automatically.
        """
        cutoff = (now if now is not None else time.time()) - self._run_ttl_seconds
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                cur = self._conn.execute(
                    "DELETE FROM runs WHERE status = ? AND updated_at < ?",
                    (RunStatus.RUNNING.value, cutoff),
                )
                self._conn.commit()
                return cur.rowcount or 0
            except Exception:
                self._conn.rollback()
                raise


def _row_to_record(row: sqlite3.Row) -> RunRecord:
    """Build a :class:`RunRecord` from a raw SQLite row."""
    return RunRecord(
        run_id=row["run_id"],
        agent_name=row["agent_name"],
        tenant_id=row["tenant_id"],
        status=RunStatus(row["status"]),
        input_payload=json.loads(row["input_json"]),
        output=(json.loads(row["output_json"]) if row["output_json"] else None),
        error=row["error"],
        attempts=row["attempts"],
        max_retries=row["max_retries"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        duration_ms=row["duration_ms"],
    )


__all__ = ["RunNotCancellableError", "RunNotFoundError", "RunRecord", "RunStatus", "StateStore"]
