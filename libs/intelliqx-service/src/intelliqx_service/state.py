"""SQLite-backed run state store.

Stores run records in a single table; exposes enqueue/claim_next/
complete/cancel/get primitives. Concurrency is serialised by a
single ``check_same_thread=False`` connection plus an internal
mutex, which is fine for a single-node worker; multi-process would
need a proper queue.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class RunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class RunRecord:
    run_id: str
    agent_name: str
    tenant_id: str
    status: RunStatus
    input_payload: dict[str, Any]
    output: dict[str, Any] | None
    error: str | None
    attempts: int
    created_at: float
    updated_at: float
    duration_ms: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "agent_name": self.agent_name,
            "tenant_id": self.tenant_id,
            "status": self.status.value,
            "input": self.input_payload,
            "output": self.output,
            "error": self.error,
            "attempts": self.attempts,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "duration_ms": self.duration_ms,
        }


class StateStore:
    """Thread-safe SQLite run queue + status table."""

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
    CREATE INDEX IF NOT EXISTS idx_runs_status_updated ON runs(status, updated_at);
    """

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._is_memory = self._path == ":memory:"
        self._conn = sqlite3.connect(  # type: ignore[call-overload]
            self._path, check_same_thread=False, uri=self._path if self._is_memory else None
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(self.SCHEMA)
        self._conn.commit()
        self._lock = threading.Lock()

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
        now = time.time()
        with self._lock:
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

    def claim_next(
        self, worker_count: int, max_retries: int
    ) -> tuple[str, str, dict[str, Any], str, int] | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT run_id, agent_name, input_json, tenant_id, attempts "
                "FROM runs WHERE status = ? ORDER BY created_at ASC LIMIT 1",
                (RunStatus.PENDING.value,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            run_id, agent, input_json, tenant_id, attempts = row
            self._conn.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ?",
                (RunStatus.RUNNING.value, time.time(), run_id),
            )
            self._conn.commit()
            return (run_id, agent, json.loads(input_json), tenant_id, int(attempts) + 1)

    def complete(
        self,
        run_id: str,
        status: RunStatus,
        output: dict[str, Any] | None = None,
        error: str | None = None,
        duration_ms: int = 0,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE runs SET status = ?, output_json = ?, error = ?, "
                "duration_ms = ?, updated_at = ? WHERE run_id = ?",
                (
                    status.value,
                    json.dumps(output) if output is not None else None,
                    error,
                    duration_ms,
                    time.time(),
                    run_id,
                ),
            )
            self._conn.commit()

    def requeue(self, run_id: str, next_attempt: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE runs SET status = ?, attempts = ?, updated_at = ? " "WHERE run_id = ?",
                (RunStatus.PENDING.value, next_attempt, time.time(), run_id),
            )
            self._conn.commit()

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("SELECT status FROM runs WHERE run_id = ?", (run_id,))
            row = cur.fetchone()
            if row is None or row["status"] not in {
                RunStatus.PENDING.value,
                RunStatus.RUNNING.value,
            }:
                return False
            self._conn.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ?",
                (RunStatus.CANCELLED.value, time.time(), run_id),
            )
            self._conn.commit()
            return True

    def get(self, run_id: str) -> RunRecord | None:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
            row = cur.fetchone()
            if row is None:
                return None
            return RunRecord(
                run_id=row["run_id"],
                agent_name=row["agent_name"],
                tenant_id=row["tenant_id"],
                status=RunStatus(row["status"]),
                input_payload=json.loads(row["input_json"]),
                output=(json.loads(row["output_json"]) if row["output_json"] else None),
                error=row["error"],
                attempts=row["attempts"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                duration_ms=row["duration_ms"],
            )


__all__ = ["RunRecord", "RunStatus", "StateStore"]
