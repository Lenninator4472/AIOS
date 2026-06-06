"""
AI-DOS Kernel: System Monitor Service
Polls /proc/stat and /proc/meminfo every 5 seconds, computes health thresholds,
and emits events on the bus.
"""

import os
import threading
import time
from datetime import datetime

from kernel.bus import EventBus
from kernel.service import Service


class SystemMonitor(Service):
    """
    Daemon service that monitors system CPU and memory usage.

    Polls /proc/stat and /proc/meminfo every *interval* seconds, computes
    resource usage percentages, evaluates health thresholds, and emits
    corresponding events on the bus.

    Emitted events::

        system.monitor.tick      — every cycle with full payload
        system.health.ok         — CPU <= 75% and memory <= 80%
        system.health.warning    — CPU > 75% or memory > 80%
        system.health.critical   — CPU > 90% or memory > 90%

    Health state is the worst of CPU and memory thresholds.
    """

    def __init__(self, bus: EventBus, interval: float = 5.0):
        super().__init__("monitor", bus)
        self._interval = interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

        # CPU tracking
        self._prev_total = 0
        self._prev_idle = 0
        self._first_sample = True

        # Current snapshot
        self._snapshot = {
            "cpu_percent": 0.0,
            "mem_percent": 0.0,
            "mem_total_mb": 0.0,
            "mem_used_mb": 0.0,
            "health": "ok",
            "timestamp": datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _on_start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def _on_stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_snapshot(self) -> dict:
        """Return the latest monitoring snapshot as a dict.

        Returns:
            dict with keys: ``cpu_percent``, ``mem_percent``,
            ``mem_total_mb``, ``mem_used_mb``, ``health``, ``timestamp``.
        """
        with self._lock:
            return dict(self._snapshot)

    # ------------------------------------------------------------------
    # Poll loop
    # ------------------------------------------------------------------

    def _poll_loop(self):
        while not self._stop_event.is_set():
            self._poll_once()
            self._stop_event.wait(self._interval)

    def _poll_once(self):
        cpu_percent = self._read_cpu()
        mem_total_kb, mem_avail_kb, _ = self._read_memory()

        if mem_total_kb > 0:
            mem_percent = (mem_total_kb - mem_avail_kb) / mem_total_kb * 100.0
            mem_used_mb = (mem_total_kb - mem_avail_kb) / 1024.0
            mem_total_mb = mem_total_kb / 1024.0
        else:
            mem_percent = 0.0
            mem_used_mb = 0.0
            mem_total_mb = 0.0

        health = self._compute_health(cpu_percent, mem_percent)
        timestamp = datetime.now().isoformat()

        with self._lock:
            self._snapshot = {
                "cpu_percent": round(cpu_percent, 1),
                "mem_percent": round(mem_percent, 1),
                "mem_total_mb": round(mem_total_mb, 1),
                "mem_used_mb": round(mem_used_mb, 1),
                "health": health,
                "timestamp": timestamp,
            }

        self._bus.emit("system.monitor.tick", dict(self._snapshot))
        self._bus.emit(f"system.health.{health}", {
            "cpu_percent": round(cpu_percent, 1),
            "mem_percent": round(mem_percent, 1),
            "timestamp": timestamp,
        })

    # ------------------------------------------------------------------
    # /proc parsing
    # ------------------------------------------------------------------

    def _read_cpu(self) -> float:
        """Read /proc/stat and compute CPU usage % since last sample.

        Returns 0.0 on the first sample (no delta available) or on error.
        """
        try:
            with open("/proc/stat", "r") as f:
                line = f.readline()
        except (FileNotFoundError, PermissionError, OSError):
            return 0.0

        if not line.startswith("cpu "):
            return 0.0

        parts = line.split()
        if len(parts) < 5:
            return 0.0

        # fields: user nice system idle iowait irq softirq steal ...
        idle = int(parts[4])
        total = sum(int(v) for v in parts[1:])

        if self._first_sample:
            self._prev_total = total
            self._prev_idle = idle
            self._first_sample = False
            return 0.0

        delta_total = total - self._prev_total
        delta_idle = idle - self._prev_idle

        self._prev_total = total
        self._prev_idle = idle

        if delta_total == 0:
            return 0.0

        return (delta_total - delta_idle) / delta_total * 100.0

    def _read_memory(self):
        """Read /proc/meminfo and return (total_kb, available_kb, free_kb).

        Returns (0, 0, 0) on error.
        """
        total = 0
        available = 0
        free = 0

        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        total = self._parse_kb_value(line)
                    elif line.startswith("MemAvailable:"):
                        available = self._parse_kb_value(line)
                    elif line.startswith("MemFree:"):
                        free = self._parse_kb_value(line)
        except (FileNotFoundError, PermissionError, OSError):
            pass

        return total, available, free

    @staticmethod
    def _parse_kb_value(line: str) -> int:
        """Parse a ``/proc/meminfo`` line like ``MemTotal: 16384000 kB``."""
        parts = line.split()
        if len(parts) >= 2:
            try:
                return int(parts[1])
            except ValueError:
                pass
        return 0

    # ------------------------------------------------------------------
    # Health computation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_health(cpu_percent: float, mem_percent: float) -> str:
        """Return the worst health level based on CPU and memory thresholds.

        Thresholds:
            - CPU > 90% or memory > 90%   → ``critical``
            - CPU > 75% or memory > 80%   → ``warning``
            - otherwise                   → ``ok``
        """
        if cpu_percent > 90 or mem_percent > 90:
            return "critical"
        if cpu_percent > 75 or mem_percent > 80:
            return "warning"
        return "ok"
