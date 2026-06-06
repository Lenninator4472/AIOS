"""
AI-DOS Kernel: Long-term Fact Memory
Persistent key-value fact store with keyword search.
Zero external dependencies (uses JSON + sqlite3).
"""

import json
import os
import sqlite3
import re
from datetime import datetime
from typing import List, Dict, Optional


HOME = os.path.expanduser("~")
MEMORY_DIR = os.path.join(HOME, ".ai-dos", "memory")
FACTS_DB = os.path.join(MEMORY_DIR, "facts.db")


class FactMemory:
    """
    Persistent fact storage with keyword tagging and search.
    Stores structured facts: text + tags + source + timestamp.
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path or FACTS_DB
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                tags TEXT DEFAULT '',
                source TEXT DEFAULT 'conversation',
                created_at TEXT DEFAULT (datetime('now')),
                access_count INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_facts_tags ON facts(tags)
        """)
        conn.commit()
        conn.close()

    def remember(self, text: str, tags: List[str] = None, source: str = "conversation") -> int:
        """Store a fact. Returns the fact ID."""
        tags_str = ",".join(tags) if tags else ""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "INSERT INTO facts (text, tags, source, created_at) VALUES (?, ?, ?, ?)",
            (text.strip(), tags_str, source, datetime.now().isoformat())
        )
        fact_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return fact_id

    def recall(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Search facts by keyword matching.
        Matches against both text and tags.
        Returns list of fact dicts sorted by relevance.
        """
        words = re.findall(r'\w+', query.lower())
        if not words:
            return []

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT id, text, tags, source, created_at, access_count FROM facts")
        results = []
        for row in cursor.fetchall():
            fact_text = row[1].lower()
            fact_tags = row[2].lower()
            score = 0
            for word in words:
                if len(word) < 3:
                    continue
                if word in fact_text:
                    score += fact_text.count(word) * 2
                if word in fact_tags:
                    score += 5
            if score > 0:
                results.append({
                    "id": row[0],
                    "text": row[1],
                    "tags": row[2].split(",") if row[2] else [],
                    "source": row[3],
                    "created_at": row[4],
                    "access_count": row[5],
                    "score": score,
                })

        conn.close()

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def forget(self, fact_id: int) -> bool:
        """Delete a fact by ID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def list_all(self, limit: int = 20) -> List[Dict]:
        """List most recent facts."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT id, text, tags, source, created_at FROM facts ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0],
                "text": row[1],
                "tags": row[2].split(",") if row[2] else [],
                "source": row[3],
                "created_at": row[4],
            })
        conn.close()
        return results

    def count(self) -> int:
        """Total number of stored facts."""
        conn = sqlite3.connect(self.db_path)
        count = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        conn.close()
        return count

    def record_access(self, fact_id: int):
        """Increment access count for a fact."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE facts SET access_count = access_count + 1 WHERE id = ?", (fact_id,))
        conn.commit()
        conn.close()
