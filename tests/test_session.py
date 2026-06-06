"""Tests for kernel/session.py — Session Manager."""

import json
import os
import tempfile

from kernel.session import SessionManager


class TestSessionManager:
    """SessionManager: create, switch, delete, rename, persistence."""

    def test_constructor_creates_default_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(sessions_dir=tmpdir)
            assert "default" in sm.names()
            assert sm.current == "default"

    def test_create_new_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(sessions_dir=tmpdir)
            assert sm.create("work") is True
            assert "work" in sm.names()

    def test_create_duplicate_returns_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(sessions_dir=tmpdir)
            assert sm.create("work") is True
            assert sm.create("work") is False

    def test_switch_to_existing_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(sessions_dir=tmpdir)
            sm.create("work")
            assert sm.switch("work") is True
            assert sm.current == "work"

    def test_switch_to_nonexistent_returns_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(sessions_dir=tmpdir)
            assert sm.switch("nope") is False

    def test_add_message_appends_to_current(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(sessions_dir=tmpdir)
            sm.add_message({"role": "user", "content": "hello"})
            assert len(sm.current_messages) == 1
            assert sm.current_messages[0]["content"] == "hello"

    def test_messages_are_isolated_per_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(sessions_dir=tmpdir)
            sm.add_message({"role": "user", "content": "msg1"})
            sm.create("work")
            sm.switch("work")
            sm.add_message({"role": "user", "content": "msg2"})
            assert sm.current_messages[0]["content"] == "msg2"
            assert sm.info("default")["message_count"] == 1

    def test_delete_removes_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(sessions_dir=tmpdir)
            sm.create("temp")
            assert sm.delete("temp") is True
            assert "temp" not in sm.names()

    def test_delete_default_returns_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(sessions_dir=tmpdir)
            assert sm.delete("default") is False

    def test_delete_switches_to_default_when_current_deleted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(sessions_dir=tmpdir)
            sm.create("temp")
            sm.switch("temp")
            sm.delete("temp")
            assert sm.current == "default"

    def test_rename_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(sessions_dir=tmpdir)
            sm.create("old")
            assert sm.rename("old", "new") is True
            assert "old" not in sm.names()
            assert "new" in sm.names()

    def test_rename_default_returns_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(sessions_dir=tmpdir)
            assert sm.rename("default", "renamed") is False

    def test_rename_to_existing_returns_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(sessions_dir=tmpdir)
            sm.create("a")
            sm.create("b")
            assert sm.rename("a", "b") is False

    def test_rename_updates_current(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(sessions_dir=tmpdir)
            sm.create("old")
            sm.switch("old")
            sm.rename("old", "new")
            assert sm.current == "new"

    def test_info_returns_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(sessions_dir=tmpdir)
            info = sm.info("default")
            assert info["name"] == "default"
            assert "message_count" in info
            assert "created_at" in info
            assert "updated_at" in info

    def test_info_for_nonexistent_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(sessions_dir=tmpdir)
            info = sm.info("nope")
            assert info["name"] == "nope"
            assert info["message_count"] == 0

    def test_current_messages_setter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(sessions_dir=tmpdir)
            sm.current_messages = [{"role": "system", "content": "test"}]
            assert len(sm.current_messages) == 1
            assert sm.current_messages[0]["content"] == "test"

    def test_save_and_reload_persists_messages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm1 = SessionManager(sessions_dir=tmpdir)
            sm1.add_message({"role": "user", "content": "persist me"})
            sm1.create("work")
            sm1.switch("work")
            sm1.add_message({"role": "assistant", "content": "ok"})
            sm1.save_all()

            sm2 = SessionManager(sessions_dir=tmpdir)
            assert sm2.info("default")["message_count"] == 1
            assert sm2.info("work")["message_count"] == 1
            assert sm2.current_messages[0]["content"] == "persist me"

    def test_persistence_survives_restart_with_multiple_sessions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm1 = SessionManager(sessions_dir=tmpdir)
            sm1.create("alpha")
            sm1.create("beta")
            sm1.switch("alpha")
            sm1.add_message({"role": "user", "content": "alpha msg"})
            sm1.switch("beta")
            sm1.add_message({"role": "user", "content": "beta msg"})
            sm1.save_all()

            sm2 = SessionManager(sessions_dir=tmpdir)
            assert sm2.info("alpha")["message_count"] == 1
            assert sm2.info("beta")["message_count"] == 1
            # Switch to alpha and verify message content
            sm2.switch("alpha")
            assert sm2.current_messages[0]["content"] == "alpha msg"

    def test_session_dir_created_automatically(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sub = os.path.join(tmpdir, "sessions")
            assert not os.path.exists(sub)
            sm = SessionManager(sessions_dir=sub)
            assert os.path.isdir(sub)
            assert "default" in sm.names()
