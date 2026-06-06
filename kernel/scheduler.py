"""
AI-DOS Kernel: Background Task Scheduler
Run shell commands in background threads with lifecycle tracking.
"""

import enum
import os
import signal
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from typing import Optional

from kernel.bus import EventBus
from kernel.service import Service


class TaskStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskInfo:
    """Snapshot of a scheduled background task."""

    task_id: str
    command: str
    status: TaskStatus = TaskStatus.PENDING
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    pid: Optional[int] = None


class BackgroundTaskScheduler(Service):
    """Schedules and tracks shell commands running in background threads.

    Emits ``task.started``, ``task.completed``, and ``task.failed`` events.
    """

    def __init__(self, bus: EventBus):
        super().__init__("scheduler", bus)
        self._tasks: dict[str, TaskInfo] = {}
        self._procs: dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()

    def schedule(self, command: str) -> str:
        """Schedule *command* to run in a background thread.

        Returns the task ID (UUID hex string).
        """
        tid = uuid.uuid4().hex
        info = TaskInfo(task_id=tid, command=command)

        with self._lock:
            self._tasks[tid] = info

        self._bus.emit("task.started", {"task_id": tid, "command": command})

        thread = threading.Thread(target=self._run, args=(tid,), daemon=True)
        thread.start()

        return tid

    def get_status(self, task_id: str) -> Optional[TaskInfo]:
        """Return the :class:`TaskInfo` for *task_id*, or *None* if unknown."""
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self, status: Optional[TaskStatus] = None) -> list[TaskInfo]:
        """Return all tracked tasks, optionally filtered by *status*."""
        with self._lock:
            tasks = list(self._tasks.values())
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    def cancel(self, task_id: str) -> bool:
        """Attempt to kill a running task.

        Returns ``True`` if the task was running and killed,
        ``False`` if it was not running or is unknown.
        """
        proc = self._procs.get(task_id)
        if proc is None or proc.poll() is not None:
            return False
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return False
        return True

    def _run(self, tid: str):
        """Internal: run the command, capture output, store result."""
        with self._lock:
            info = self._tasks[tid]
            info.status = TaskStatus.RUNNING

        with subprocess.Popen(
            info.command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=os.setsid,
        ) as proc:
            with self._lock:
                self._procs[tid] = proc
                info.pid = proc.pid

            stdout, stderr = proc.communicate()
            exit_code = proc.returncode

        with self._lock:
            info.stdout = stdout or ""
            info.stderr = stderr or ""
            info.exit_code = exit_code
            info.status = TaskStatus.COMPLETED if exit_code == 0 else TaskStatus.FAILED
            self._procs.pop(tid, None)

        if exit_code == 0:
            self._bus.emit("task.completed", {"task_id": tid, "exit_code": exit_code})
        else:
            self._bus.emit(
                "task.failed",
                {"task_id": tid, "exit_code": exit_code, "stderr": info.stderr},
            )

    def health_check(self) -> dict:
        """Extend health check with task counts."""
        info = super().health_check()
        with self._lock:
            info["active_tasks"] = sum(
                1 for t in self._tasks.values() if t.status == TaskStatus.RUNNING
            )
            info["total_tasks"] = len(self._tasks)
        return info
