"""
AI-DOS Kernel: Structured JSON Logging Service
Captures all bus events, agent outputs, and tool calls to JSON lines files.
"""

import json
import os
import threading
from datetime import date, datetime
from typing import Optional

from kernel.bus import EventBus
from kernel.service import Service


_LOG_DIR = os.path.expanduser("~/.ai-dos/logs")
_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


_KNOWN_PATTERNS = [
    # Service lifecycle
    "service.*.started",
    "service.*.stopped",
    # Tasks
    "task.started",
    "task.completed",
    "task.failed",
    # System health
    "system.health.ok",
    "system.health.warning",
    "system.health.critical",
    "system.monitor.tick",
    # Autopilot
    "autopilot.action",
    # API
    "api.request",
    # File watcher
    "fs.file.created",
    "fs.file.modified",
    "fs.file.deleted",
    # Cron
    "cron.job.trigger",
]


class LoggingService(Service):
    """
    Captures all bus events as JSON lines to ``~/.ai-dos/logs/events.jsonl``.

    Features:
    -   JSON lines format (one JSON object per line).
    -   Daily rotation: a new file is started each day.
    -   Size-based rotation: once a file exceeds *max_bytes* it is renamed
        to ``.1``, previous ``.1`` to ``.2``, etc. (keeps 3 rotated copies).
    -   Subscribes to all known bus event patterns.
    """

    def __init__(self, bus: EventBus, log_dir: str | None = None,
                 max_bytes: int = _DEFAULT_MAX_BYTES,
                 event_patterns: list[str] | None = None):
        super().__init__("logger", bus)
        self._log_dir = log_dir or _LOG_DIR
        self._max_bytes = max_bytes
        self._patterns = event_patterns or _KNOWN_PATTERNS
        self._lock = threading.Lock()
        self._file: Optional[object] = None  # actually a TextIO
        self._current_date: Optional[date] = None
        os.makedirs(self._log_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _on_start(self):
        for pattern in self._patterns:
            self._bus.subscribe(pattern, self._on_event)

    def _on_stop(self):
        self.flush()

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------

    def _on_event(self, event_type: str, data):
        if not self._running:
            return
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": event_type,
            "data": data,
        }
        self._write_entry(entry)

    # ------------------------------------------------------------------
    # File management
    # ------------------------------------------------------------------

    def _get_log_path(self) -> str:
        today = date.today()
        return os.path.join(self._log_dir, f"events-{today.isoformat()}.jsonl")

    def get_log_path(self) -> str:
        """Return the current active log file path."""
        with self._lock:
            return self._get_log_path()

    def _open_file(self):
        path = self._get_log_path()
        self._current_date = date.today()
        # Open in append mode; create if missing
        self._file = open(path, "a", encoding="utf-8")

    def _close_file(self):
        if self._file is not None:
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None

    def _write_entry(self, entry: dict):
        line = json.dumps(entry, default=str) + "\n"
        with self._lock:
            try:
                today = date.today()
                if self._file is None or self._current_date != today:
                    self._close_file()
                    self._open_file()

                self._file.write(line)
                self._file.flush()

                # Check size and rotate if needed
                if self._file.tell() > self._max_bytes:
                    self._close_file()
                    self._rotate()
                    self._open_file()
            except Exception:
                pass  # Best-effort logging

    def _rotate(self):
        """Rename log files: .jsonl -> .jsonl.1, .1 -> .2, .2 -> .3."""
        base = self._get_log_path()
        for i in range(2, 0, -1):
            older = f"{base}.{i}"
            newer = f"{base}.{i - 1}" if i > 1 else base
            if os.path.exists(older if i > 1 else newer):
                try:
                    os.rename(newer, older)
                except OSError:
                    pass
        # Remove the .3 file if it exists
        for i in [3]:
            old = f"{base}.{i}"
            if os.path.exists(old):
                try:
                    os.remove(old)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # Public query API
    # ------------------------------------------------------------------

    def query(self, event_type: str | None = None,
              limit: int = 50) -> list[dict]:
        """Read log entries from the current log file.

        Args:
            event_type: If set, only return entries matching this event type.
            limit: Maximum number of entries to return.

        Returns:
            A list of parsed log entry dicts, newest first.
        """
        path = self._get_log_path()
        if not os.path.exists(path):
            return []

        entries: list[dict] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event_type is None or entry.get("event") == event_type:
                    entries.append(entry)

        entries.reverse()
        return entries[:limit]

    def flush(self):
        """Force-write any buffered data to disk."""
        with self._lock:
            if self._file is not None:
                try:
                    self._file.flush()
                except Exception:
                    pass
