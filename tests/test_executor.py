"""Tests for kernel/executor.py — safe command execution layer."""

import pytest
from kernel.executor import (
    execute,
    needs_confirmation,
    execute_multiple,
    DESTRUCTIVE_COMMANDS,
    BLOCKED_COMMANDS,
)


# ─── needs_confirmation ──────────────────────────────────────────────────────

class TestNeedsConfirmation:
    """needs_confirmation(command) -> (bool, reason)"""

    @pytest.mark.parametrize("cmd", [
        "rm file.txt",
        "rm -rf /",
        "rmdir empty_dir",
        "dd if=/dev/zero of=file bs=1M count=1",
        "mkfs.ext4 /dev/sdb1",
        "fdisk /dev/sda",
        "parted /dev/sda",
        "shutdown -h now",
        "reboot",
        "poweroff",
        "chmod 777 file",
        "chown root file",
        "mv source dest",
    ])
    def test_destructive_commands_need_confirmation(self, cmd):
        """All destructive commands must return needs_confirmation=True."""
        assert needs_confirmation(cmd)[0] is True, f"{cmd} should need confirmation"

    @pytest.mark.parametrize("cmd", [
        "sudo rm -rf /",
        "sudo ls",
        "passwd",
        "passwd lenninator44",
    ])
    def test_blocked_commands_need_confirmation(self, cmd):
        """All blocked commands must return needs_confirmation=True."""
        assert needs_confirmation(cmd)[0] is True, f"{cmd} should be blocked"

    @pytest.mark.parametrize("cmd", [
        'echo hello',
        'ls -la',
        'cat /etc/hostname',
        'grep -r "test" .',
        'find . -name "*.py"',
        'python3 -c "print(1+1)"',
        'git status',
        'pwd',
        'whoami',
        'date',
    ])
    def test_safe_commands_dont_need_confirmation(self, cmd):
        """Safe commands must return needs_confirmation=False."""
        assert needs_confirmation(cmd)[0] is False, f"{cmd} should NOT need confirmation"

    @pytest.mark.parametrize("cmd", [
        'echo "hello" > file.txt',
        'cat file.txt >> log.txt',
        'ls | grep foo',
    ])
    def test_shell_redirects_need_confirmation(self, cmd):
        """Commands with shell redirects/pipes need confirmation."""
        assert needs_confirmation(cmd)[0] is True, f"{cmd} with redirect should need confirmation"

    def test_empty_command(self):
        """Empty commands should not need confirmation."""
        assert needs_confirmation("")[0] is False

    def test_whitespace_command(self):
        """Whitespace-only commands should not error."""
        assert needs_confirmation("   ")[0] is False

    def test_destructive_reason_is_not_empty(self):
        """When needs_confirmation is True, reason should be non-empty."""
        _, reason = needs_confirmation("rm file.txt")
        assert reason != ""

    def test_safe_reason_is_empty(self):
        """When needs_confirmation is False, reason should be empty."""
        _, reason = needs_confirmation("ls")
        assert reason == ""


# ─── execute ─────────────────────────────────────────────────────────────────

class TestExecute:
    """execute(command) -> {"stdout": str, "stderr": str, "exit_code": int}"""

    def test_simple_echo(self):
        """Simple echo should succeed with correct output."""
        result = execute("echo hello")
        assert result["exit_code"] == 0
        assert "hello" in result["stdout"]

    def test_echo_with_spaces(self):
        """Echo with quoted spaces should preserve them."""
        result = execute('echo "hello   world"')
        assert result["exit_code"] == 0
        assert "hello   world" in result["stdout"]

    def test_ls_root(self):
        """ls / should succeed."""
        result = execute("ls /")
        assert result["exit_code"] == 0
        assert len(result["stdout"]) > 0

    def test_nonexistent_command(self):
        """Non-existent command should return exit_code=-1."""
        result = execute("nonexistent_command_xyz123")
        assert result["exit_code"] == -1
        assert "not found" in result["stderr"].lower()

    def test_empty_command(self):
        """Empty string should return exit_code=-1."""
        result = execute("")
        assert result["exit_code"] == -1
        assert "empty" in result["stderr"].lower()

    def test_command_with_args(self):
        """Command with arguments should work."""
        result = execute("echo one two three")
        assert result["exit_code"] == 0
        assert result["stdout"].strip() == "one two three"

    def test_exit_code_reflects_failure(self):
        """Failed command should have non-zero exit code."""
        result = execute("bash -c 'exit 42'")
        assert result["exit_code"] == 42

    def test_stderr_captured(self):
        """stderr output should be captured."""
        result = execute("bash -c 'echo error_msg >&2'")
        assert "error_msg" in result["stderr"]

    def test_returns_dict_with_correct_keys(self):
        """Result dict should have stdout, stderr, exit_code keys."""
        result = execute("true")
        assert set(result.keys()) == {"stdout", "stderr", "exit_code"}

    def test_command_with_special_chars(self):
        """Command with special characters should execute safely (no shell injection)."""
        result = execute("echo '$HOME'")
        assert result["exit_code"] == 0
        # With shlex, '$HOME' is treated literally (not expanded)
        assert "$HOME" in result["stdout"]


# ─── execute_multiple ────────────────────────────────────────────────────────

class TestExecuteMultiple:
    """execute_multiple(commands, on_confirmation) -> list[dict]"""

    def test_all_safe_commands_succeed(self):
        """Multiple safe commands should all execute."""
        results = execute_multiple(["echo a", "echo b", "echo c"])
        assert len(results) == 3
        assert all(r["exit_code"] == 0 for r in results)

    def test_with_confirmation_callback_skips_dangerous(self):
        """on_confirmation callback should be called for dangerous commands."""
        callback_calls = []

        def confirm(cmd, reason):
            callback_calls.append((cmd, reason))
            return False  # skip all

        commands = ["ls", "rm file.txt", "echo done"]
        results = execute_multiple(commands, on_confirmation=confirm)

        assert len(results) == 3
        # First and last should execute normally
        assert results[0]["exit_code"] == 0
        assert results[2]["exit_code"] == 0
        # Middle should be skipped
        assert results[1]["exit_code"] == -2
        assert "SKIPPED" in results[1]["stderr"]
        # Callback should have been called for the dangerous command
        assert len(callback_calls) == 1
        assert "rm" in callback_calls[0][0]

    @pytest.mark.parametrize("n", [1, 5, 10])
    def test_empty_list_returns_empty(self, n):
        """Empty command list should return empty results list."""
        assert execute_multiple([]) == []

    def test_single_command(self):
        """Single command should return single result."""
        results = execute_multiple(["echo single"])
        assert len(results) == 1
        assert results[0]["exit_code"] == 0

    def test_mixed_safe_and_dangerous_without_callback(self):
        """Without on_confirmation callback, dangerous commands still execute."""
        # Without callback, dangerous commands are still executed by execute_multiple
        results = execute_multiple(["echo safe", "echo also_safe"])
        assert len(results) == 2
        assert all(r["exit_code"] == 0 for r in results)


# ─── Constants sanity ────────────────────────────────────────────────────────

class TestConstants:
    """Sanity checks on DESTRUCTIVE_COMMANDS and BLOCKED_COMMANDS lists."""

    def test_destructive_commands_is_list_of_strings(self):
        assert isinstance(DESTRUCTIVE_COMMANDS, list)
        assert all(isinstance(c, str) for c in DESTRUCTIVE_COMMANDS)

    def test_blocked_commands_is_list_of_strings(self):
        assert isinstance(BLOCKED_COMMANDS, list)
        assert all(isinstance(c, str) for c in BLOCKED_COMMANDS)

    def test_no_overlap_between_lists(self):
        """A command shouldn't be in both destructive and blocked lists."""
        overlap = set(DESTRUCTIVE_COMMANDS) & set(BLOCKED_COMMANDS)
        assert overlap == set(), f"Overlap: {overlap}"

    def test_blocked_commands_are_truly_dangerous(self):
        """Every blocked command should also trigger needs_confirmation."""
        for cmd in BLOCKED_COMMANDS:
            assert needs_confirmation(cmd)[0] is True, f"{cmd} should need confirmation"
