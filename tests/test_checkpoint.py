"""Tests for kernel/checkpoint.py — State Checkpointing."""
import os
import json
import tempfile
import pytest
from unittest.mock import MagicMock, patch
from kernel.checkpoint import save_checkpoint, load_checkpoint, STATE_DIR


class TestCheckpoint:
    """Checkpoint — save and restore kernel runtime state."""

    def test_save_checkpoint_creates_file(self):
        kernel = MagicMock()
        kernel.scheduler.list_tasks.return_value = []
        kernel.orchestrator.agents = {}

        save_checkpoint(kernel)
        assert os.path.isfile(os.path.join(STATE_DIR, "checkpoint.json"))

    def test_save_checkpoint_contains_tasks(self):
        task = MagicMock()
        task.task_id = "abc123"
        task.command = "echo hello"
        task.status.value = "completed"
        task.exit_code = 0
        task.stdout = "hello\n"
        task.stderr = ""

        kernel = MagicMock()
        kernel.scheduler.list_tasks.return_value = [task]
        kernel.orchestrator.agents = {}

        save_checkpoint(kernel)
        with open(os.path.join(STATE_DIR, "checkpoint.json")) as f:
            state = json.load(f)

        assert state["scheduler"]["tasks"][0]["task_id"] == "abc123"
        assert state["scheduler"]["tasks"][0]["status"] == "completed"

    def test_save_checkpoint_contains_agents(self):
        agent = MagicMock()
        agent.messages = [{"role": "system", "content": "test"}]
        agent.session_log = [{"input": "hello", "output": {"status": "ok"}}]

        kernel = MagicMock()
        kernel.scheduler.list_tasks.return_value = []
        kernel.orchestrator.agents = {"coder": agent}

        save_checkpoint(kernel)
        with open(os.path.join(STATE_DIR, "checkpoint.json")) as f:
            state = json.load(f)

        assert "coder" in state["agents"]
        assert state["agents"]["coder"]["messages"][0]["role"] == "system"

    def test_load_checkpoint_restores_agents(self):
        agent = MagicMock()
        agent.messages = [{"role": "system", "content": "PERSISTED"}]
        agent.session_log = [{"input": "test", "output": {"ok": True}}]

        kernel = MagicMock()
        kernel.scheduler.list_tasks.return_value = []
        kernel.orchestrator.agents = {"coder": agent}
        kernel.orchestrator.get.return_value = agent

        save_checkpoint(kernel)

        agent.messages = []
        agent.session_log = []

        result = load_checkpoint(kernel)
        assert result is True
        assert len(agent.messages) > 0
        assert agent.messages[0]["content"] == "PERSISTED"
        assert len(agent.session_log) > 0

    def test_load_checkpoint_no_file_returns_false(self):
        kernel = MagicMock()
        result = load_checkpoint(kernel)
        assert result is False

    @pytest.fixture(autouse=True)
    def cleanup(self):
        yield
        path = os.path.join(STATE_DIR, "checkpoint.json")
        if os.path.isfile(path):
            os.remove(path)
