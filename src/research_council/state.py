"""SQLite state: topic leases, token usage, model cooldowns."""

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS leases (
    topic_id TEXT PRIMARY KEY, version INTEGER NOT NULL, lease_until REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, step TEXT, model TEXT,
    tokens_in INTEGER, tokens_out INTEGER, at REAL
);
CREATE TABLE IF NOT EXISTS cooldowns (model TEXT PRIMARY KEY, until REAL NOT NULL);
"""


@dataclass
class UsageRow:
    run_id: str
    step: str
    model: str
    tokens_in: int
    tokens_out: int


class State:
    def __init__(self, db_path: Path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
        self.db.executescript(SCHEMA)
        self._lock = threading.Lock()

    def _exec(self, sql: str, params: tuple = ()) -> list[tuple]:
        """All access goes through one lock: steps call the state from worker threads."""
        with self._lock:
            cur = self.db.execute(sql, params)
            rows = cur.fetchall()
            self._rowcount = cur.rowcount
            return rows

    def acquire_lease(self, topic_id: str, now: float, ttl_s: int = 1800) -> int | None:
        """Atomically take the lease if free or expired; return its new version."""
        rows = self._exec(
            """INSERT INTO leases (topic_id, version, lease_until) VALUES (?, 1, ?)
               ON CONFLICT(topic_id) DO UPDATE SET version = version + 1, lease_until = excluded.lease_until
               WHERE leases.lease_until < ?
               RETURNING version""",
            (topic_id, now + ttl_s, now),
        )
        return rows[0][0] if rows else None

    def heartbeat(self, topic_id: str, version: int, now: float, ttl_s: int = 1800) -> bool:
        rows = self._exec(
            "UPDATE leases SET lease_until = ? WHERE topic_id = ? AND version = ?",
            (now + ttl_s, topic_id, version),
        )
        return self._rowcount == 1

    def release(self, topic_id: str, version: int) -> None:
        self._exec(
            "UPDATE leases SET lease_until = 0 WHERE topic_id = ? AND version = ?",
            (topic_id, version),
        )

    def lease_active(self, topic_id: str, now: float) -> bool:
        rows = self._exec("SELECT lease_until FROM leases WHERE topic_id = ?", (topic_id,))
        return bool(rows and rows[0][0] > now)

    def record_usage(self, run_id, step, model, tokens_in, tokens_out, now: float) -> None:
        self._exec(
            "INSERT INTO usage (run_id, step, model, tokens_in, tokens_out, at) VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, step, model, tokens_in, tokens_out, now),
        )

    def usage_for_run(self, run_id: str) -> list[UsageRow]:
        rows = self._exec(
            "SELECT run_id, step, model, tokens_in, tokens_out FROM usage WHERE run_id = ? ORDER BY id",
            (run_id,),
        )
        return [UsageRow(*r) for r in rows]

    def calls_since(self, model: str, since: float) -> int:
        rows = self._exec("SELECT COUNT(*) FROM usage WHERE model = ? AND at >= ?", (model, since))
        return rows[0][0]

    def set_cooldown(self, model: str, until: float) -> None:
        self._exec(
            "INSERT INTO cooldowns (model, until) VALUES (?, ?) ON CONFLICT(model) DO UPDATE SET until = excluded.until",
            (model, until),
        )

    def in_cooldown(self, model: str, now: float) -> bool:
        rows = self._exec("SELECT until FROM cooldowns WHERE model = ?", (model,))
        return bool(rows and rows[0][0] > now)
