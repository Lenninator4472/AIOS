"""
AI-DOS Kernel: Autonomous Agent / Autopilot
Subscribes to system and task events, auto-diagnoses failures via LLM,
and logs all actions for review.
"""

import threading
import time
from datetime import datetime
from typing import Callable

from kernel.bus import EventBus
from kernel.service import Service
from kernel.llm import get_provider


class AutoPilot(Service):
    """
    Autonomous agent that monitors bus events and reacts to failures.

    Subscribes to ``task.failed``, ``task.completed``,
    ``system.health.warning``, and ``system.health.critical`` events.

    On ``task.failed`` the autopilot uses the LLM to analyse stderr + command
    and suggest a fix.  On ``system.health.critical`` it emits
    ``autopilot.action`` with a suggested remediation.

    All analyses are performed in **background daemon threads** so the event
    bus is never blocked.
    """

    def __init__(self, name: str, bus: EventBus, llm_provider: Callable = None):
        super().__init__(name, bus)
        self._llm_provider = llm_provider or get_provider
        self._lock = threading.Lock()
        self._action_log: list[dict] = []
        self._max_log_size = 100

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _on_start(self):
        self._bus.subscribe("task.failed", self._on_task_failed)
        self._bus.subscribe("task.completed", self._on_task_completed)
        self._bus.subscribe("system.health.warning", self._on_health_warning)
        self._bus.subscribe("system.health.critical", self._on_health_critical)

    def _on_stop(self):
        # Bus unsubscribe is best-effort; the handler checks _running internally
        pass

    # ------------------------------------------------------------------
    # Event handlers (called on bus thread — spawn background analysis)
    # ------------------------------------------------------------------

    def _on_task_failed(self, event_type: str, data: dict):
        if not self._running:
            return
        threading.Thread(
            target=self._analyze_task_failure,
            args=(data,),
            daemon=True,
        ).start()

    def _on_task_completed(self, event_type: str, data: dict):
        if not self._running:
            return
        self._log_action("task.completed", data, analysis=None, action="logged")

    def _on_health_warning(self, event_type: str, data: dict):
        if not self._running:
            return
        self._log_action("system.health.warning", data, analysis=None, action="noted")

    def _on_health_critical(self, event_type: str, data: dict):
        if not self._running:
            return
        threading.Thread(
            target=self._analyze_health_critical,
            args=(data,),
            daemon=True,
        ).start()

    # ------------------------------------------------------------------
    # Background analysis
    # ------------------------------------------------------------------

    def _analyze_task_failure(self, data: dict):
        task_id = data.get("task_id", "?")
        command = data.get("command", "")
        stderr = data.get("stderr", "")

        prompt = (
            f"A task failed. Command: {command}\n"
            f"stderr: {stderr[:500]}\n"
            "Suggest a fix in one short sentence."
        )
        try:
            llm = self._llm_provider()
            analysis = llm.query(
                "You are a diagnostic assistant. Be concise.",
                prompt,
            )
        except Exception as e:
            analysis = f"[LLM error] {e}"

        action = f"Suggested fix for task {task_id}"
        self._log_action("task.failed", data, analysis=analysis, action=action)

    def _analyze_health_critical(self, data: dict):
        cpu = data.get("cpu_percent", 0)
        mem = data.get("mem_percent", 0)

        prompt = (
            f"System health is CRITICAL. CPU: {cpu}%, Memory: {mem}%.\n"
            "Suggest one short remediation action."
        )
        try:
            llm = self._llm_provider()
            analysis = llm.query(
                "You are a system administrator assistant. Be concise.",
                prompt,
            )
        except Exception as e:
            analysis = f"[LLM error] {e}"

        remediation = f"Suggested remediation for critical health (CPU={cpu}%, MEM={mem}%)"

        # Emit a remediation action on the bus
        self._bus.emit("autopilot.action", {
            "analysis": analysis,
            "action": remediation,
            "cpu_percent": cpu,
            "mem_percent": mem,
            "timestamp": datetime.now().isoformat(),
        })

        self._log_action("system.health.critical", data, analysis=analysis, action=remediation)

    # ------------------------------------------------------------------
    # Action log
    # ------------------------------------------------------------------

    def _log_action(self, event: str, data: dict, analysis: str | None, action: str):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": event,
            "data": data,
            "analysis": analysis,
            "action": action,
        }
        with self._lock:
            self._action_log.append(entry)
            if len(self._action_log) > self._max_log_size:
                self._action_log.pop(0)

    def get_action_log(self, limit: int = 10) -> list[dict]:
        """Return the most recent *limit* action log entries."""
        with self._lock:
            return list(self._action_log[-limit:])

    def get_stats(self) -> dict:
        """Return a dict mapping event types to occurrence counts."""
        with self._lock:
            counts: dict[str, int] = {}
            for entry in self._action_log:
                event = entry["event"]
                counts[event] = counts.get(event, 0) + 1
            return counts
