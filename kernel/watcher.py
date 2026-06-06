"""
AI-DOS Kernel: File Watcher Service
Polls watched directories for file system changes (create, modify, delete).
"""

import os
import threading
import time
from datetime import datetime
from typing import List

from kernel.bus import EventBus
from kernel.service import Service


class FileWatcher(Service):
    """
    Polls a list of directories for file changes and emits events on the bus.

    Events::

        fs.file.created   → {"path": ..., "timestamp": ...}
        fs.file.modified  → {"path": ..., "timestamp": ...}
        fs.file.deleted   → {"path": ..., "timestamp": ...}

    Default watched directories: ``[~/Downloads, ~/ai-dos]``.
    """

    def __init__(self, bus: EventBus, interval: float = 2.0,
                 directories: list[str] | None = None):
        super().__init__("watcher", bus)
        self._interval = interval
        if directories is not None:
            self._directories = list(directories)
        else:
            self._directories = [
                os.path.expanduser("~/Downloads"),
                os.path.expanduser("~/ai-dos"),
            ]
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

        # _mtimes: path -> last mtime
        self._mtimes: dict[str, float] = {}

        # _recent_changes: list of event dicts
        self._recent_changes: list[dict] = []
        self._max_recent = 100

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _on_start(self):
        self._scan_all()  # Initial snapshot
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def _on_stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_watch(self, path: str):
        """Add a directory to the watch list.

        An initial scan is performed immediately so that future polls
        only report changes from this point forward.
        """
        path = os.path.abspath(os.path.expanduser(path))
        with self._lock:
            if path not in self._directories:
                self._directories.append(path)
        self._scan_directory(path)

    def remove_watch(self, path: str) -> bool:
        """Remove a directory from the watch list.

        Returns ``True`` if the directory was actually removed.
        """
        path = os.path.abspath(os.path.expanduser(path))
        with self._lock:
            if path in self._directories:
                self._directories.remove(path)
                # Clean up stored mtimes for files in this directory
                prefix = path.rstrip("/") + "/"
                stale = [p for p in self._mtimes if p.startswith(prefix)]
                for p in stale:
                    del self._mtimes[p]
                return True
            return False

    def get_watched_dirs(self) -> list[str]:
        """Return the list of currently watched directories."""
        with self._lock:
            return list(self._directories)

    def get_recent_changes(self, limit: int = 20) -> list[dict]:
        """Return the most recent *limit* file change events."""
        with self._lock:
            return list(self._recent_changes[-limit:])

    # ------------------------------------------------------------------
    # Poll loop
    # ------------------------------------------------------------------

    def _poll_loop(self):
        while not self._stop_event.is_set():
            self._poll_once()
            self._stop_event.wait(self._interval)

    def _poll_once(self):
        with self._lock:
            dirs = list(self._directories)

        for directory in dirs:
            if not os.path.isdir(directory):
                continue
            self._scan_directory(directory)

    def _scan_all(self):
        """Scan all watched directories to build initial mtime index."""
        with self._lock:
            dirs = list(self._directories)
        for directory in dirs:
            if os.path.isdir(directory):
                self._scan_directory(directory)

    def _scan_directory(self, directory: str):
        """Compare current file listings with stored mtimes and emit events."""
        try:
            current_entries: dict[str, float] = {}
            for entry in os.listdir(directory):
                full_path = os.path.join(directory, entry)
                try:
                    st = os.stat(full_path)
                    if os.path.isfile(full_path):
                        current_entries[full_path] = st.st_mtime
                except OSError:
                    continue

            with self._lock:
                prev_mtimes = dict(self._mtimes)

            # Detect created and modified files
            for path, mtime in current_entries.items():
                if path not in prev_mtimes:
                    self._emit_change("fs.file.created", path)
                elif prev_mtimes[path] != mtime:
                    self._emit_change("fs.file.modified", path)

            # Detect deleted files
            for path in prev_mtimes:
                if path not in current_entries:
                    self._emit_change("fs.file.deleted", path)

            # Update stored mtimes
            with self._lock:
                for path in current_entries:
                    self._mtimes[path] = current_entries[path]
                # Remove stale entries
                for path in list(self._mtimes):
                    if path not in current_entries:
                        del self._mtimes[path]

        except PermissionError:
            pass

    def _emit_change(self, event_type: str, path: str):
        timestamp = datetime.now().isoformat()
        data = {"path": path, "timestamp": timestamp}
        self._bus.emit(event_type, data)

        with self._lock:
            self._recent_changes.append({"event": event_type, **data})
            if len(self._recent_changes) > self._max_recent:
                self._recent_changes.pop(0)
