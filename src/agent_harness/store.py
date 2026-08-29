from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


class RunStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _migrate(self) -> None:
        with self._connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError(f"Database schema {version} is newer than supported version {SCHEMA_VERSION}")
            if version < 1:
                db.executescript("""
                    CREATE TABLE runs (
                        id TEXT PRIMARY KEY,
                        label TEXT NOT NULL,
                        suite TEXT NOT NULL,
                        model TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        passed INTEGER NOT NULL,
                        summary_json TEXT NOT NULL,
                        report_json TEXT NOT NULL
                    );
                    CREATE TABLE reviews (
                        id TEXT PRIMARY KEY,
                        run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                        case_id TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        decision TEXT,
                        notes TEXT NOT NULL DEFAULT '',
                        reviewer TEXT NOT NULL DEFAULT '',
                        version INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        reviewed_at TEXT,
                        payload_json TEXT NOT NULL,
                        UNIQUE(run_id, case_id)
                    );
                    CREATE INDEX reviews_status_idx ON reviews(status);
                    PRAGMA user_version = 1;
                """)

    def ingest_report(self, report: dict[str, Any], label: str | None = None) -> str:
        run_id = uuid.uuid4().hex
        models = sorted({result.get("model", "unknown") for result in report.get("results", [])})
        summary = report.get("summary", {})
        created = report.get("finished_at") or datetime.now(UTC).isoformat()
        run_label = label or report.get("metadata", {}).get("run_label") or run_id[:8]
        with self._connect() as db:
            db.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, run_label, report["suite_name"], ", ".join(models), created, int(bool(summary.get("passed"))), json.dumps(summary), json.dumps(report)),
            )
            for result in report.get("results", []):
                if not result.get("needs_review"):
                    continue
                review_id = uuid.uuid4().hex
                payload = {
                    "prompt": result.get("prompt"),
                    "output": result.get("output"),
                    "confidence": result.get("confidence"),
                    "metrics": result.get("metrics", {}),
                    "findings": result.get("findings", []),
                    "trace": result.get("trace", []),
                    "capsule": result.get("capsule", {}),
                }
                db.execute(
                    "INSERT INTO reviews (id, run_id, case_id, created_at, payload_json) VALUES (?, ?, ?, ?, ?)",
                    (review_id, run_id, result["case_id"], created, json.dumps(payload)),
                )
        return run_id

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT id, label, suite, model, created_at, passed, summary_json FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [{**dict(row), "passed": bool(row["passed"]), "summary": json.loads(row["summary_json"])} for row in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT report_json FROM runs WHERE id = ?", (run_id,)).fetchone()
        return json.loads(row["report_json"]) if row else None

    def list_reviews(self, status: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT id, run_id, case_id, status, decision, notes, reviewer, version, created_at, reviewed_at, payload_json FROM reviews"
        params: tuple[Any, ...] = ()
        if status:
            sql += " WHERE status = ?"
            params = (status,)
        sql += " ORDER BY created_at DESC"
        with self._connect() as db:
            rows = db.execute(sql, params).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]

    def decide_review(self, review_id: str, decision: str, notes: str, reviewer: str, expected_version: int) -> dict[str, Any]:
        if decision not in {"pass", "fail", "ambiguous"}:
            raise ValueError("decision must be pass, fail, or ambiguous")
        now = datetime.now(UTC).isoformat()
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE reviews SET status='reviewed', decision=?, notes=?, reviewer=?, reviewed_at=?, version=version+1 WHERE id=? AND version=?",
                (decision, notes, reviewer, now, review_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Review was modified by another reviewer; reload before saving")
        return next(item for item in self.list_reviews() if item["id"] == review_id)
