"""Tests for kernel/tool_context.py — Tool Sandbox / ToolContext."""

import time
from kernel.tool_context import ToolContext, dangerous


class TestToolContext:
    """ToolContext: execution, timeout, dangerous marking, truncation."""

    def test_successful_execution_returns_ok_true(self):
        tc = ToolContext(timeout=5.0)

        def add(a, b):
            return a + b

        result = tc.execute(add, 2, 3)
        assert result["ok"] is True
        assert result["error"] is None
        assert "5" in result["result"]

    def test_successful_execution_returns_result(self):
        tc = ToolContext()

        def greet(name):
            return f"Hello, {name}!"

        result = tc.execute(greet, "World")
        assert result["ok"] is True
        assert result["result"] == "Hello, World!"

    def test_exception_in_function_returns_ok_false(self):
        tc = ToolContext()

        def broken():
            raise ValueError("something went wrong")

        result = tc.execute(broken)
        assert result["ok"] is False
        assert result["error"] is not None
        assert "something went wrong" in result["error"]

    def test_timeout_kills_long_running_function(self):
        tc = ToolContext(timeout=0.1)

        def slow():
            time.sleep(10)

        result = tc.execute(slow)
        assert result["ok"] is False
        assert "timed out" in result["error"].lower()

    def test_dangerous_decorator_marks_function(self):
        @dangerous
        def delete_file():
            return "deleted"

        assert ToolContext.is_dangerous(delete_file) is True

    def test_is_dangerous_returns_false_for_undecorated(self):
        def safe_func():
            return "safe"

        assert ToolContext.is_dangerous(safe_func) is False

    def test_truncate_shortens_long_results(self):
        short = "hello"
        assert ToolContext.truncate(short, limit=10) == "hello"

        long_str = "a" * 100
        truncated = ToolContext.truncate(long_str, limit=10)
        assert len(truncated) == 13  # 10 chars + "..."
        assert truncated.endswith("...")

    def test_truncate_does_not_shorten_within_limit(self):
        text = "short text"
        assert ToolContext.truncate(text, limit=100) == text

    def test_duration_is_measured_in_ms(self):
        tc = ToolContext()

        def quick():
            return "done"

        result = tc.execute(quick)
        assert isinstance(result["duration_ms"], float)
        assert result["duration_ms"] > 0

    def test_execute_with_args_and_kwargs(self):
        tc = ToolContext()

        def repeat(text, times=1):
            return text * times

        result = tc.execute(repeat, "ha", times=3)
        assert result["ok"] is True
        assert result["result"] == "hahaha"

    def test_result_size_limit_applied(self):
        tc = ToolContext(result_limit=10)

        def big():
            return "x" * 1000

        result = tc.execute(big)
        assert len(result["result"]) == 13  # 10 + "..."
        assert result["result"].endswith("...")
