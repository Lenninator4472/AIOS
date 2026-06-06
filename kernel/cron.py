"""
AI-DOS Kernel: Cron Service
A cron-like scheduler for recurring tasks, persisted to SQLite.
"""

import os
import re
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from kernel.bus import EventBus
from kernel.service import Service


_CRON_DB = os.path.expanduser("~/.ai-dos/cron.db")


def _parse_cron_field(field: str, min_val: int, max_val: int) -> set[int]:
    """Parse a single cron field and return the set of matching values.

    Supports ``*``, a bare number, comma-separated numbers (``1,15``),
    and step notation (``*/5``).  The result is constrained to
    ``[min_val, max_val]``.
    """
    if field == "*":
        return set(range(min_val, max_val + 1))

    # Step notation: */N, 1-10/2, etc.
    if "/" in field:
        base, step_str = field.split("/", 1)
        try:
            step = int(step_str)
        except ValueError:
            return set()
        if step <= 0:
            return set()
        if base == "*":
            return set(range(min_val, max_val + 1, step))
        # Range like 1-10/2
        if "-" in base:
            parts = base.split("-")
            try:
                lo, hi = int(parts[0]), int(parts[1])
            except ValueError:
                return set()
            return set(range(max(lo, min_val), min(hi, max_val) + 1, step))
        return set()

    # Comma-separated numbers
    if "," in field:
        values: set[int] = set()
        for part in field.split(","):
            if "-" in part:
                parts = part.split("-")
                try:
                    lo, hi = int(parts[0]), int(parts[1])
                    values.update(range(max(lo, min_val), min(hi, max_val) + 1))
                except ValueError:
                    continue
            else:
                try:
                    values.add(int(part))
                except ValueError:
                    continue
        return {v for v in values if min_val <= v <= max_val}

    # Single number
    try:
        v = int(field)
        if min_val <= v <= max_val:
            return {v}
    except ValueError:
        pass

    return set()


def parse_cron_expression(expr: str) -> dict | None:
    """Parse a 5-field cron expression ``minute hour day month weekday``.

    Returns a dict with keys ``minute``, ``hour``, ``day``, ``month``,
    ``weekday``, each containing a ``set[int]`` of matching values,
    or ``None`` if the expression is invalid.
    """
    parts = expr.strip().split()
    if len(parts) != 5:
        return None

    field_names = ["minute", "hour", "day", "month", "weekday"]
    ranges = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]
    result = {}

    for name, (lo, hi), raw in zip(field_names, ranges, parts):
        values = _parse_cron_field(raw, lo, hi)
        if not values:
            return None
        result[name] = values

    return result


def cron_matches(parsed: dict, dt: datetime | None = None) -> bool:
    """Check whether *parsed* cron expression matches the given datetime.

    If *dt* is ``None`` the current UTC time is used.
    """
    if dt is None:
        dt = datetime.utcnow()
    return (
        dt.minute in parsed["minute"]
        and dt.hour in parsed["hour"]
        and dt.day in parsed["day"]
        and dt.month in parsed["month"]
        and dt.weekday() in parsed["weekday"]
    )


def next_run(parsed: dict, after: datetime | None = None) -> datetime | None:
    """Calculate the next datetime at which *parsed* will match.

    Searches forward up to one year from *after* (default: now).
    Returns ``None`` if no match is found in that window.
    """
    if after is None:
        after = datetime.utcnow()
    # Start at the next minute
    candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    deadline = after + timedelta(days=365)
    while candidate <= deadline:
        if cron_matches(parsed, candidate):
            return candidate
        candidate += timedelta(minutes=1)
    return None


class CronService(Service):
    """
    Cron-like scheduler that runs recurring tasks on the bus.

    Jobs are persisted to SQLite (``~/.ai-dos/cron.db``) and survive
    restarts.  A background thread ticks every 30 seconds, checks which
    jobs should run, and emits ``cron.job.trigger`` events.
    """

    def __init__(self, bus: EventBus, db_path: str | None = None):
        super().__init__("cron", bus)
        self._db_path = db_path or _CRON_DB
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._init_db()

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    def _init_db(self):
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cron_jobs (
                job_id TEXT PRIMARY KEY,
                expression TEXT NOT NULL,
                command TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _on_start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._tick_loop, daemon=True)
        self._thread.start()

    def _on_stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def schedule(self, expression: str, command: str) -> str:
        """Schedule a cron job.

        Args:
            expression: A 5-field cron expression (``"* * * * *"``).
            command: The shell command to run when triggered.

        Returns:
            A unique job ID string.

        Raises:
            ValueError: If the cron expression is invalid.
        """
        parsed = parse_cron_expression(expression)
        if parsed is None:
            raise ValueError(f"Invalid cron expression: {expression}")

        job_id = uuid.uuid4().hex
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            "INSERT INTO cron_jobs (job_id, expression, command) VALUES (?, ?, ?)",
            (job_id, expression, command),
        )
        conn.commit()
        conn.close()
        return job_id

    def unschedule(self, job_id: str) -> bool:
        """Remove a scheduled cron job.

        Returns:
            ``True`` if the job existed and was removed.
        """
        conn = sqlite3.connect(self._db_path)
        cursor = conn.execute("DELETE FROM cron_jobs WHERE job_id = ?", (job_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def list_jobs(self) -> list[dict]:
        """Return all scheduled cron jobs as a list of dicts."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.execute(
            "SELECT job_id, expression, command, created_at FROM cron_jobs"
        )
        rows = []
        for row in cursor.fetchall():
            rows.append({
                "job_id": row[0],
                "expression": row[1],
                "command": row[2],
                "created_at": row[3],
            })
        conn.close()
        return rows

    def get_next_runs(self, count: int = 5) -> list[Tuple[str, str, str]]:
        """Return the next *count* scheduled run times.

        Returns a list of ``(job_id, command, next_run_time_iso)`` tuples.
        """
        jobs = self.list_jobs()
        now = datetime.utcnow()
        upcoming: list[Tuple[datetime, str, str, str]] = []

        for job in jobs:
            parsed = parse_cron_expression(job["expression"])
            if parsed is None:
                continue
            nxt = next_run(parsed, now)
            if nxt is not None:
                upcoming.append((nxt, job["job_id"], job["command"], nxt.isoformat()))

        upcoming.sort(key=lambda x: x[0])
        return [(jid, cmd, ts) for _, jid, cmd, ts in upcoming[:count]]

    # ------------------------------------------------------------------
    # Tick loop
    # ------------------------------------------------------------------

    def _tick_loop(self):
        while not self._stop_event.is_set():
            self._tick()
            self._stop_event.wait(30)

    def _tick(self):
        now = datetime.utcnow()
        jobs = self.list_jobs()
        for job in jobs:
            parsed = parse_cron_expression(job["expression"])
            if parsed is None:
                continue
            if cron_matches(parsed, now):
                self._bus.emit("cron.job.trigger", {
                    "job_id": job["job_id"],
                    "command": job["command"],
                    "expression": job["expression"],
                    "timestamp": now.isoformat(),
                })
