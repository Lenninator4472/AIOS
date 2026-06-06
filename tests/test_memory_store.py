"""Tests for kernel/memory_store.py — long-term fact memory."""
import os
import tempfile
import pytest
from kernel.memory_store import FactMemory


@pytest.fixture
def mem():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    fm = FactMemory(db_path=db_path)
    yield fm
    os.unlink(db_path)


class TestFactMemory:
    """FactMemory — remember, recall, forget, list."""

    def test_remember_and_recall(self, mem):
        mem.remember("User likes dark mode", tags=["preference", "ui"])
        mem.remember("User is a student at Maestro College", tags=["education"])
        results = mem.recall("dark mode")
        assert len(results) >= 1
        assert "dark" in results[0]["text"].lower()

    def test_recall_returns_scored_results(self, mem):
        mem.remember("Python is a programming language")
        mem.remember("The user prefers Python for scripting")
        results = mem.recall("Python programming")
        assert len(results) >= 1
        assert results[0]["score"] > 0

    def test_forget_removes_fact(self, mem):
        fid = mem.remember("Test fact to forget")
        assert mem.forget(fid) is True
        results = mem.recall("test fact")
        assert len(results) == 0

    def test_forget_nonexistent(self, mem):
        assert mem.forget(99999) is False

    def test_list_all(self, mem):
        mem.remember("Fact one")
        mem.remember("Fact two")
        mem.remember("Fact three")
        facts = mem.list_all(limit=10)
        assert len(facts) >= 3

    def test_count(self, mem):
        assert mem.count() == 0
        mem.remember("Hello world")
        assert mem.count() == 1
        mem.remember("Another fact")
        assert mem.count() == 2

    def test_recall_empty_query(self, mem):
        mem.remember("Some fact")
        assert mem.recall("") == []

    def test_recall_no_match(self, mem):
        mem.remember("Python is great")
        assert mem.recall("quantum physics") == []

    def test_tags_are_searchable(self, mem):
        mem.remember("User's name is Matthew", tags=["identity", "name"])
        results = mem.recall("identity")
        assert len(results) >= 1
        assert "Matthew" in results[0]["text"]
