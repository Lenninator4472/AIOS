"""
AI-DOS Kernel: Tool Sandbox / ToolContext
A safe wrapper for executing tool/plugin functions with timeout,
exception isolation, and result size limiting.
"""

import functools
import threading
import time
from typing import Any, Callable


def dangerous(func: Callable) -> Callable:
    """Decorator that marks a function as dangerous/destructive.

    Tools marked with ``@dangerous`` will require user confirmation
    before execution in secure contexts.

    Example::

        @dangerous
        def tool_delete_file(path: str) -> str:
            ...
    """
    func._dangerous = True  # type: ignore[attr-defined]
    return func


class ToolContext:
    """
    Wraps a callable with safety guards: timeout, exception isolation,
    and result size limiting.

    Usage::

        tc = ToolContext(timeout=10.0)
        result = tc.execute(my_func, arg1, arg2)
        # -> {"ok": True, "result": "...", "error": None, "duration_ms": 12.34}
    """

    def __init__(self, timeout: float = 30.0, result_limit: int = 10000):
        self._timeout = timeout
        self._result_limit = result_limit

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, func: Callable, *args: Any, **kwargs: Any) -> dict:
        """Execute *func* with *args*/*kwargs* under safety guards.

        Returns a dict::

            {"ok": bool, "result": str, "error": str | None, "duration_ms": float}

        *   ``ok`` is ``True`` if the function returned without raising.
        *   ``result`` is the string representation of the return value,
            truncated to *result_limit* characters.
        *   ``error`` contains the exception message on failure, else ``None``.
        *   ``duration_ms`` is the wall-clock execution time in milliseconds.
        """
        start = time.perf_counter()
        result_container: list = []
        error_container: list = []
        finished = threading.Event()

        def target():
            try:
                ret = func(*args, **kwargs)
                result_container.append(ret)
            except Exception as e:
                error_container.append(e)
            finally:
                finished.set()

        worker = threading.Thread(target=target, daemon=True)
        worker.start()

        ok = finished.wait(timeout=self._timeout)
        elapsed = (time.perf_counter() - start) * 1000.0

        if not ok:
            # Timeout — the thread is still running (daemon, will be abandoned)
            return {
                "ok": False,
                "result": "",
                "error": f"Execution timed out after {self._timeout}s",
                "duration_ms": round(elapsed, 2),
            }

        if error_container:
            return {
                "ok": False,
                "result": "",
                "error": str(error_container[0]),
                "duration_ms": round(elapsed, 2),
            }

        raw = result_container[0] if result_container else None
        if raw is None:
            result_str = ""
        elif isinstance(raw, str):
            result_str = raw
        else:
            result_str = str(raw)

        result_str = self.truncate(result_str, self._result_limit)

        return {
            "ok": True,
            "result": result_str,
            "error": None,
            "duration_ms": round(elapsed, 2),
        }

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def is_dangerous(func: Callable) -> bool:
        """Check whether *func* has been marked with the ``@dangerous`` decorator."""
        return getattr(func, "_dangerous", False)

    @staticmethod
    def truncate(text: str, limit: int = 10000) -> str:
        """Truncate *text* to at most *limit* characters, appending ``...``."""
        if len(text) <= limit:
            return text
        return text[:limit] + "..."
