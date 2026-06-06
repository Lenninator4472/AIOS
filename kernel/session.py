"""
AI-DOS Kernel: Session Manager
Named conversational sessions with isolated message contexts,
persisted as JSON files under ~/.ai-dos/sessions/.
"""

import json
import os
from datetime import datetime


SESSIONS_DIR = os.path.expanduser("~/.ai-dos/sessions")


class SessionManager:
    """Manages named conversational sessions with isolated message contexts.

    Each session stores a list of messages, creation timestamp, and
    last-updated timestamp.  Sessions are auto-saved to individual JSON files
    on every switch or mutation.

    Usage::

        sm = SessionManager()
        sm.create("work")
        sm.switch("work")
        sm.add_message({"role": "user", "content": "hello"})
        sm.current_messages  # -> list
    """

    def __init__(self, sessions_dir: str | None = None):
        self._sessions_dir = sessions_dir or SESSIONS_DIR
        os.makedirs(self._sessions_dir, exist_ok=True)
        self._sessions: dict = {}
        self._current = "default"
        self._load_all()
        if "default" not in self._sessions:
            self._create_default()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def current(self) -> str:
        """Name of the currently active session."""
        return self._current

    @property
    def current_messages(self) -> list:
        """Message list for the current session."""
        return self._sessions[self._current]["messages"]

    @current_messages.setter
    def current_messages(self, value: list):
        self._sessions[self._current]["messages"] = value

    # ------------------------------------------------------------------
    # Session operations
    # ------------------------------------------------------------------

    def names(self) -> list[str]:
        """Return sorted list of all session names."""
        return sorted(self._sessions.keys())

    def create(self, name: str) -> bool:
        """Create a new empty session.

        Returns ``True`` if created, ``False`` if the name already exists.
        """
        if name in self._sessions:
            return False
        now = datetime.now().isoformat()
        self._sessions[name] = {
            "messages": [],
            "created_at": now,
            "updated_at": now,
        }
        self._save(name)
        return True

    def switch(self, name: str) -> bool:
        """Switch to a different session.

        The previous session is saved to disk first.
        Returns ``True`` on success, ``False`` if the session does not exist.
        """
        if name not in self._sessions:
            return False
        self._save(self._current)
        self._current = name
        return True

    def delete(self, name: str) -> bool:
        """Delete a session.

        The *default* session cannot be deleted.
        Returns ``True`` on success.
        """
        if name not in self._sessions or name == "default":
            return False
        del self._sessions[name]
        path = self._path(name)
        if os.path.exists(path):
            os.remove(path)
        if self._current == name:
            self._current = "default"
        return True

    def rename(self, old: str, new: str) -> bool:
        """Rename a session.

        The *default* session cannot be renamed.
        Returns ``True`` on success.
        """
        if old not in self._sessions or new in self._sessions or old == "default":
            return False
        self._sessions[new] = self._sessions.pop(old)
        self._sessions[new]["updated_at"] = datetime.now().isoformat()
        old_path = self._path(old)
        if os.path.exists(old_path):
            os.remove(old_path)
        self._save(new)
        if self._current == old:
            self._current = new
        return True

    def add_message(self, msg: dict):
        """Append a message to the current session and update its timestamp."""
        self._sessions[self._current]["messages"].append(msg)
        self._sessions[self._current]["updated_at"] = datetime.now().isoformat()

    def info(self, name: str | None = None) -> dict:
        """Return metadata dict for a given session (defaults to current)."""
        name = name or self._current
        s = self._sessions.get(name, {})
        return {
            "name": name,
            "message_count": len(s.get("messages", [])),
            "created_at": s.get("created_at", ""),
            "updated_at": s.get("updated_at", ""),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_all(self):
        """Save all in-memory sessions to disk."""
        for name in list(self._sessions.keys()):
            self._save(name)

    def _create_default(self):
        now = datetime.now().isoformat()
        self._sessions["default"] = {
            "messages": [],
            "created_at": now,
            "updated_at": now,
        }
        self._save("default")

    def _path(self, name: str) -> str:
        safe = name.replace("/", "_").replace("\\", "_")
        return os.path.join(self._sessions_dir, f"{safe}.json")

    def _save(self, name: str):
        if name in self._sessions:
            path = self._path(name)
            with open(path, "w") as f:
                json.dump(self._sessions[name], f, default=str)

    def _load_all(self):
        if not os.path.isdir(self._sessions_dir):
            return
        for fname in sorted(os.listdir(self._sessions_dir)):
            if not fname.endswith(".json"):
                continue
            name = fname[:-5]
            path = os.path.join(self._sessions_dir, fname)
            try:
                with open(path) as f:
                    data = json.load(f)
                if isinstance(data, dict) and "messages" in data:
                    self._sessions[name] = data
            except Exception:
                pass
