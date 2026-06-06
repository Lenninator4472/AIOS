"""
AI-DOS Kernel: Conversation Memory & Account Profiles
Sliding window context management with SQLite persistence and user accounts.
"""

import json
import os
import sqlite3
from typing import List, Dict, Optional
from datetime import datetime


class ConversationMemory:
    """
    Maintains conversation history as a sliding window and manages
    the persistent AI-DOS user account layer.
    """

    def __init__(self, max_exchanges: int = 10, db_path: str = None):
        self.max_exchanges = max_exchanges
        self.history: List[Dict] = []
        self.db_path = db_path or os.path.expanduser("~/.ai-dos/memory.db")
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        
        # 1. Chat History Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                role TEXT,
                content TEXT
            )
        """)
        
        # 2. User Account Profile Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS account_profile (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()
        conn.close()

    def add(self, role: str, content: str, persist: bool = True):
        """Add a message to history."""
        self.history.append({"role": role, "content": content})

        # Trim to sliding window
        if len(self.history) > self.max_exchanges * 2:
            self.history = self.history[-(self.max_exchanges * 2):]

        if persist:
            self._persist(role, content)

    def _persist(self, role: str, content: str):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT INTO conversations (timestamp, role, content) VALUES (?, ?, ?)",
                (datetime.now().isoformat(), role, json.dumps(content) if isinstance(content, dict) else content)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def get_context(self) -> List[Dict]:
        """Get the current conversation context for LLM."""
        return self.history

    def clear(self):
        """Clear in-memory history."""
        self.history = []

    # --- ACCOUNT PROFILE MANAGEMENT METHODS ---

    def get_profile(self) -> Dict[str, str]:
        """Fetch all key-value pairs representing the user's account profile."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute("SELECT key, value FROM account_profile")
            profile = {row[0]: row[1] for row in cursor.fetchall()}
            conn.close()
            return profile
        except Exception:
            return {}

    def update_profile_field(self, key: str, value: str):
        """Insert or update an individual profile vector in the database."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT OR REPLACE INTO account_profile (key, value) VALUES (?, ?)",
                (key, value)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def initialize_default_account(self):
        """Set up standard default account parameters if fields don't exist."""
        profile = self.get_profile()
        defaults = {
            "username": "lenninator44",
            "real_name": "Matthew Leonard",
            "system_role": "Lead Software Architect / L1 DevOps Engineer",
            "primary_stack": "Flutter / Dart / Python / Bash",
            "preferred_model": "llama3.2:1b"
        }
        for key, val in defaults.items():
            if key not in profile:
                self.update_profile_field(key, val)
