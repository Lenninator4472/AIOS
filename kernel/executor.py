"""
AI-DOS Kernel: Safe Command Execution Layer
Executes bash commands with safety guards. No shell=True.
"""

import os
import re
import shlex
import subprocess
from typing import List, Tuple


# Dry-run mode: when True, commands are validated but not executed
DRY_RUN = False

def set_dry_run(enabled: bool):
    global DRY_RUN
    DRY_RUN = enabled

def is_dry_run() -> bool:
    return DRY_RUN

# Safe paths recommended for daily work
HOME = os.path.expanduser("~")
RECOMMENDED_PATHS = [
    HOME,
    "/tmp",
    os.path.join(HOME, "Downloads"),
    os.path.join(HOME, "ai-dos"),
    os.path.join(HOME, ".ai-dos"),
]

# Paths that are always blocked (system integrity)
BLOCKED_SYSTEM_PATHS = [
    "/proc",
    "/sys",
    "/dev",
    "/boot",
    "/root",
    "/etc/shadow",
    "/etc/gshadow",
    "/etc/sudoers",
    ".ssh",
]

# Commands that access sensitive system paths
BLOCKED_PATTERNS = [
    "/etc/shadow", "/etc/gshadow", "/etc/sudoers",
    ".ssh/id_rsa", ".ssh/id_ed25519",
]


def check_path_safety(command: str) -> Tuple[bool, str]:
    """Check command for blocked system paths. Returns (is_safe, reason)."""
    for pattern in BLOCKED_SYSTEM_PATHS:
        escaped = re.escape(pattern)
        if re.search(rf'(?<!\w){escaped}(?:/|\s|$)', command):
            return False, f"Access to system path '{pattern}' is blocked"
    return True, ""

# Commands that require explicit user confirmation before execution
DESTRUCTIVE_COMMANDS = [
    "rm", "rmdir", "dd", "mkfs", "format",
    "fdisk", "parted", ">", ">>", "|",
    "shutdown", "reboot", "poweroff", "init",
    "chmod", "chown", "mv",  # mv is destructive (can overwrite)
]

# Commands that are always blocked
BLOCKED_COMMANDS = [
    "sudo",  # No privilege escalation without explicit user intent
    "passwd",  # No password changes
]

# Commands that access files outside safe paths (legacy, kept for reference)
BLOCKED_PATTERNS = []


def needs_confirmation(command: str) -> Tuple[bool, str]:
    """
    Check if a command is potentially destructive.
    Returns (needs_confirmation, reason).
    """
    tokens = shlex.split(command)

    # Check for shell redirects and pipes (they can destroy files)
    has_destructive_redirect = any(t in command for t in [">", ">>", "|"])
    if has_destructive_redirect:
        for token in tokens:
            if token.startswith(">") or token.startswith("|"):
                return True, "Shell redirect can overwrite files"

    # Check base command and sub-variants (e.g. mkfs.ext4 matches mkfs)
    if tokens:
        base = tokens[0]
        if base in BLOCKED_COMMANDS:
            return True, f"'{base}' is blocked by kernel security policy"

        for dangerous in DESTRUCTIVE_COMMANDS:
            if base == dangerous or dangerous in tokens:
                return True, f"'{base}' can permanently remove or modify data"
            # Sub-variant matching: mkfs.ext4, mkfs.btrfs, etc. all match "mkfs"
            if base.startswith(dangerous + ".") or base.startswith(dangerous + "-"):
                return True, f"'{base}' can permanently remove or modify data"

    return False, ""


def execute(command: str) -> dict:
    """
    Execute a command via subprocess.
    Returns {"stdout": str, "stderr": str, "exit_code": int}.

    Uses shlex.split() not shell=True for injection safety.
    Respects DRY_RUN mode and SAFE_PATHS.
    """
    # Check path safety first
    path_safe, path_reason = check_path_safety(command)
    if not path_safe:
        return {
            "stdout": "",
            "stderr": f"BLOCKED by path sandbox: {path_reason}",
            "exit_code": -3,
        }

    try:
        tokens = shlex.split(command)
    except ValueError as e:
        return {
            "stdout": "",
            "stderr": f"Command parsing error: {e}",
            "exit_code": -1,
        }

    if not tokens:
        return {"stdout": "", "stderr": "Empty command", "exit_code": -1}

    if DRY_RUN:
        return {
            "stdout": f"(dry-run) would execute: {command}",
            "stderr": "",
            "exit_code": 0,
        }

    try:
        result = subprocess.run(
            tokens,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }
    except FileNotFoundError:
        return {
            "stdout": "",
            "stderr": f"Command not found: {tokens[0]}",
            "exit_code": -1,
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Command timed out after 60s: {command[:60]}",
            "exit_code": -1,
        }
    except PermissionError:
        return {
            "stdout": "",
            "stderr": f"Permission denied: {tokens[0]}",
            "exit_code": -1,
        }


def execute_multiple(commands: List[str], on_confirmation: callable = None) -> List[dict]:
    """
    Execute multiple commands sequentially.
    If on_confirmation is provided, it's called with (command, reason) for destructive commands.
    Returns list of result dicts.
    """
    results = []
    for cmd in commands:
        needs_confirm, reason = needs_confirmation(cmd)
        if needs_confirm and on_confirmation:
            should_run = on_confirmation(cmd, reason)
            if not should_run:
                results.append({
                    "stdout": "",
                    "stderr": f"SKIPPED: {reason}",
                    "exit_code": -2,  # -2 = skipped
                })
                continue
        results.append(execute(cmd))
    return results
