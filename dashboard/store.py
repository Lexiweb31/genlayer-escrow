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

    _TRANSACTION_STATUS_RANKS = {
        "PENDING": 0,
        "UNINITIALIZED": 0,
        "SUBMITTED": 0,
        "ACTIVATED": 1,
        "PROPOSING": 1,
        "COMMITTING": 2,
        "REVEALING": 3,
        "ACCEPTED": 4,
        "APPEAL_COMMITTING": 5,
        "APPEAL_REVEALING": 6,
        "READY_TO_FINALIZE": 7,
        "FINALIZED": 8,
        "CANCELED": 8,
        "UNDETERMINED": 8,
        "VALIDATORS_TIMEOUT": 8,
        "LEADER_TIMEOUT": 8,
        "FAILED": 8,
        "REJECTED": 8,
    }
    _TERMINAL_TRANSACTION_STATUSES = {
        "FINALIZED",
        "CANCELED",
        "UNDETERMINED",
        "VALIDATORS_TIMEOUT",
        "LEADER_TIMEOUT",
        "FAILED",
        "REJECTED",
    }

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
        "reconcile_state",
        "reconcile_attempted_at",
        "reconcile_error_code",
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
                    reconcile_state TEXT NOT NULL DEFAULT 'IDLE',
                    reconcile_attempted_at TEXT,
                    reconcile_error_code TEXT NOT NULL DEFAULT '',
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
            if "reconcile_state" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN reconcile_state TEXT NOT NULL DEFAULT 'IDLE'")
            if "reconcile_attempted_at" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN reconcile_attempted_at TEXT")
            if "reconcile_error_code" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN reconcile_error_code TEXT NOT NULL DEFAULT ''")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    network TEXT NOT NULL,
                    tx_hash TEXT NOT NULL,
                    job_address TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    status_rank INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    verified_at TEXT,
                    UNIQUE(network, tx_hash)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_transactions_pending ON transactions(status_rank, updated_at)"
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
        attempted_at = item.get("reconcile_attempted_at")
        try:
            attempted = datetime.fromisoformat(str(attempted_at).replace("Z", "+00:00"))
            if attempted.tzinfo is None:
                attempted = attempted.replace(tzinfo=timezone.utc)
            item["reconcile_age_seconds"] = max(
                0, int((datetime.now(timezone.utc) - attempted).total_seconds())
            )
        except (TypeError, ValueError):
            item["reconcile_age_seconds"] = None
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
            "reconcile_state": str(record.get("reconcile_state") or "IDLE"),
            "reconcile_attempted_at": record.get("reconcile_attempted_at"),
            "reconcile_error_code": str(record.get("reconcile_error_code") or ""),
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

    @staticmethod
    def _transaction_row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["tx_hash"] = item["tx_hash"].lower()
        try:
            item["payload"] = json.loads(item.pop("payload_json") or "{}")
        except json.JSONDecodeError:
            item["payload"] = {}
        return item

    @classmethod
    def _transaction_values(cls, record: dict[str, Any]) -> dict[str, Any]:
        required = ("network", "tx_hash", "job_address", "kind", "status")
        missing = [field for field in required if not str(record.get(field) or "").strip()]
        if missing:
            raise ValueError(f"Missing transaction fields: {missing}")
        status_value = getattr(record["status"], "value", record["status"])
        status = str(status_value).upper()
        if status == "CANCELLED":
            status = "CANCELED"
        try:
            status_rank = cls._TRANSACTION_STATUS_RANKS[status]
        except KeyError as exc:
            raise ValueError(f"Unsupported transaction status: {status}") from exc
        return {
            "network": str(record["network"]),
            "tx_hash": str(record["tx_hash"]).lower(),
            "job_address": str(record["job_address"]),
            "kind": str(record["kind"]),
            "status": status,
            "status_rank": status_rank,
            "payload_json": json.dumps(record, default=str),
            "verified_at": record.get("verified_at"),
        }

    def record_transaction(self, record: dict[str, Any]) -> dict[str, Any]:
        """Persist one verified transaction without allowing status regression."""
        values = self._transaction_values(record)
        now = utc_now()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM transactions WHERE network = ? AND lower(tx_hash) = ?",
                (values["network"], values["tx_hash"]),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO transactions (
                        network, tx_hash, job_address, kind, status, status_rank,
                        payload_json, created_at, updated_at, verified_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        values["network"], values["tx_hash"], values["job_address"],
                        values["kind"], values["status"], values["status_rank"],
                        values["payload_json"], now, now, values["verified_at"],
                    ),
                )
            else:
                if (
                    existing["job_address"].lower() != values["job_address"].lower()
                    or existing["kind"] != values["kind"]
                ):
                    raise ValueError("Transaction hash is already associated with another job or kind")
                if values["status_rank"] > existing["status_rank"]:
                    conn.execute(
                        """
                        UPDATE transactions
                        SET status = ?, status_rank = ?, payload_json = ?, updated_at = ?,
                            verified_at = COALESCE(?, verified_at)
                        WHERE id = ?
                        """,
                        (
                            values["status"], values["status_rank"], values["payload_json"],
                            now, values["verified_at"], existing["id"],
                        ),
                    )
            row = conn.execute(
                "SELECT * FROM transactions WHERE network = ? AND lower(tx_hash) = ?",
                (values["network"], values["tx_hash"]),
            ).fetchone()
        if row is None:
            raise RuntimeError(f"Transaction {values['tx_hash']} was not persisted")
        return self._transaction_row(row)

    def get_transaction(self, network: str, tx_hash: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM transactions WHERE network = ? AND lower(tx_hash) = ?",
                (network, str(tx_hash).lower()),
            ).fetchone()
        return self._transaction_row(row) if row else None

    def list_pending_transactions(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = int(limit)
        if limit < 1:
            return []
        terminal_statuses = tuple(self._TERMINAL_TRANSACTION_STATUSES)
        placeholders = ", ".join("?" for _ in terminal_statuses)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM transactions
                WHERE status NOT IN ({placeholders})
                ORDER BY updated_at ASC
                LIMIT ?
                """,
                (*terminal_statuses, limit),
            ).fetchall()
        return [self._transaction_row(row) for row in rows]
