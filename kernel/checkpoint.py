"""
AI-DOS Kernel: State Checkpointing
Save/restore kernel runtime state to disk.
"""

import json
import os
from datetime import datetime

STATE_DIR = os.path.expanduser("~/.ai-dos/state")


def save_checkpoint(kernel) -> str:
    """Save kernel runtime state (scheduler tasks, agent contexts) to disk.
    Returns the checkpoint file path.
    """
    os.makedirs(STATE_DIR, exist_ok=True)

    state = {
        "timestamp": datetime.now().isoformat(),
        "scheduler": {
            "tasks": [
                {
                    "task_id": t.task_id,
                    "command": t.command,
                    "status": t.status.value,
                    "exit_code": t.exit_code,
                    "stdout": t.stdout,
                    "stderr": t.stderr,
                }
                for t in kernel.scheduler.list_tasks()
            ]
        },
        "agents": {
            name: {
                "messages": agent.messages,
                "session_log": agent.session_log,
            }
            for name, agent in kernel.orchestrator.agents.items()
        },
    }

    path = os.path.join(STATE_DIR, "checkpoint.json")
    with open(path, "w") as f:
        json.dump(state, f, indent=2)
    return path


def load_checkpoint(kernel) -> bool:
    """Restore kernel state from the last checkpoint.
    Returns True if a checkpoint was found and loaded.
    """
    path = os.path.join(STATE_DIR, "checkpoint.json")
    if not os.path.isfile(path):
        return False

    try:
        with open(path) as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False

    agents_data = state.get("agents", {})
    for name, data in agents_data.items():
        agent = kernel.orchestrator.get(name)
        if agent is None:
            continue
        if "messages" in data and isinstance(data["messages"], list):
            agent.messages = data["messages"]
        if "session_log" in data and isinstance(data["session_log"], list):
            agent.session_log = data["session_log"]

    tasks = state.get("scheduler", {}).get("tasks", [])
    running = [t for t in tasks if t.get("status") == "running"]
    if running:
        # Can't restore actual processes, but log the gap
        pass

    return True
