"""Durable SQLite marketplace registry for Merit.

Render deployments should set ``PERSIST_DATA_DIR`` to the mount path of a
persistent disk. Local development falls back to ``.data/`` in the repository.
Existing JSON registry entries are imported once as read-only legacy contracts;
the source file is never deleted or rewritten.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


ROOT = Path(__file__).parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    """Small synchronous SQLite store with one connection per operation."""

    _UPDATABLE = {
        "title",
        "specification",
        "client_address",
        "worker_address",
        "job_type",
        "max_submissions",
        "lifecycle_status",
        "deployment_tx",
        "settlement_json",
        "state_json",
        "updated_at",
    }

    def __init__(self, data_dir: Optional[Path | str] = None):
        configured = data_dir or os.getenv("PERSIST_DATA_DIR")
        self.data_dir = Path(configured).expanduser() if configured else ROOT / ".data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "merit_jobs.sqlite3"
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    address TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    specification TEXT NOT NULL,
                    fee_bps INTEGER NOT NULL,
                    min_score INTEGER NOT NULL,
                    partial_floor INTEGER NOT NULL,
                    job_type TEXT NOT NULL DEFAULT 'DIRECT_HIRE',
                    max_submissions INTEGER NOT NULL DEFAULT 0,
                    client_address TEXT NOT NULL DEFAULT '',
                    worker_address TEXT NOT NULL DEFAULT '',
                    lifecycle_status TEXT NOT NULL DEFAULT 'UNKNOWN',
                    deployment_tx TEXT NOT NULL DEFAULT '',
                    settlement_json TEXT NOT NULL DEFAULT '{}',
                    state_json TEXT NOT NULL DEFAULT '{}',
                    legacy_contract INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
            if "state_json" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN state_json TEXT NOT NULL DEFAULT '{}'")
            if "job_type" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN job_type TEXT NOT NULL DEFAULT 'DIRECT_HIRE'")
            if "max_submissions" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN max_submissions INTEGER NOT NULL DEFAULT 0")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC)"
            )

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["spec"] = item.pop("specification")
        item["legacy_contract"] = bool(item["legacy_contract"])
        try:
            item["settlement"] = json.loads(item.pop("settlement_json") or "{}")
        except json.JSONDecodeError:
            item["settlement"] = {"transfer_status": "RECORD_INVALID"}
        try:
            item["state_snapshot"] = json.loads(item.pop("state_json") or "{}")
        except json.JSONDecodeError:
            item["state_snapshot"] = {}
        item["explorer"] = f"https://explorer-bradbury.genlayer.com/address/{item['address']}"
        return item

    def add_job(self, record: dict[str, Any], *, ignore_existing: bool = False) -> dict[str, Any]:
        now = utc_now()
        values = {
            "id": str(record.get("id") or record["address"]),
            "address": str(record["address"]),
            "title": str(record.get("title") or "Escrow job"),
            "specification": str(record.get("specification") or record.get("spec") or ""),
            "fee_bps": int(record.get("fee_bps", 200)),
            "min_score": int(record.get("min_score", 70)),
            "partial_floor": int(record.get("partial_floor", 40)),
            "job_type": str(record.get("job_type") or "DIRECT_HIRE"),
            "max_submissions": int(record.get("max_submissions") or 0),
            "client_address": str(record.get("client_address") or ""),
            "worker_address": str(record.get("worker_address") or ""),
            "lifecycle_status": str(record.get("lifecycle_status") or record.get("status") or "UNKNOWN"),
            "deployment_tx": str(record.get("deployment_tx") or ""),
            "settlement_json": json.dumps(record.get("settlement") or {}, default=str),
            "state_json": json.dumps(record.get("state_snapshot") or {}, default=str),
            "legacy_contract": int(bool(record.get("legacy_contract"))),
            "created_at": str(record.get("created_at") or now),
            "updated_at": str(record.get("updated_at") or now),
        }
        verb = "INSERT OR IGNORE" if ignore_existing else "INSERT"
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        with self._connect() as conn:
            conn.execute(
                f"{verb} INTO jobs ({columns}) VALUES ({placeholders})",
                tuple(values.values()),
            )
        found = self.get_job(values["address"])
        if found is None:
            raise RuntimeError(f"Job {values['address']} was not persisted")
        return found

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        return [self._row(row) for row in rows]

    def get_job(self, job_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ? OR lower(address) = lower(?)",
                (job_id, job_id),
            ).fetchone()
        return self._row(row) if row else None

    def update_job(self, job_id: str, **changes: Any) -> dict[str, Any]:
        if "spec" in changes:
            changes["specification"] = changes.pop("spec")
        if "settlement" in changes:
            changes["settlement_json"] = json.dumps(changes.pop("settlement"), default=str)
        if "state_snapshot" in changes:
            changes["state_json"] = json.dumps(changes.pop("state_snapshot"), default=str)
        changes["updated_at"] = utc_now()
        unknown = set(changes) - self._UPDATABLE
        if unknown:
            raise ValueError(f"Unsupported job fields: {sorted(unknown)}")
        assignments = ", ".join(f"{column} = ?" for column in changes)
        with self._connect() as conn:
            cursor = conn.execute(
                f"UPDATE jobs SET {assignments} WHERE id = ? OR lower(address) = lower(?)",
                (*changes.values(), job_id, job_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(job_id)
        found = self.get_job(job_id)
        if found is None:
            raise KeyError(job_id)
        return found

    def import_legacy_records(self, records: Iterable[dict[str, Any]]) -> int:
        imported = 0
        for source in records:
            if not source.get("address") and not source.get("id"):
                continue
            address = str(source.get("address") or source["id"])
            existed = self.get_job(address) is not None
            record = {
                **source,
                "id": str(source.get("id") or address),
                "address": address,
                "legacy_contract": True,
                "lifecycle_status": "LEGACY_UNSAFE",
                "settlement": {
                    "transfer_status": "LEGACY_UNSAFE",
                    "warning": "Legacy settlement contract — do not fund",
                },
            }
            self.add_job(record, ignore_existing=True)
            imported += int(not existed)
        return imported
