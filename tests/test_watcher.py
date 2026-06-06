"""Tests for kernel/watcher.py — File Watcher Service."""

import os
import tempfile
import time
from kernel.bus import EventBus
from kernel.watcher import FileWatcher


class TestFileWatcher:
    """FileWatcher: directory watching, file change detection."""

    def test_constructor_sets_name(self):
        bus = EventBus()
        fw = FileWatcher(bus)
        assert fw.name == "watcher"

    def test_is_a_service(self):
        bus = EventBus()
        fw = FileWatcher(bus)
        assert hasattr(fw, "start")
        assert hasattr(fw, "stop")
        assert hasattr(fw, "health_check")

    def test_add_watch_and_get_watched_dirs(self):
        bus = EventBus()
        fw = FileWatcher(bus, directories=[])
        assert fw.get_watched_dirs() == []

        with tempfile.TemporaryDirectory() as tmpdir:
            fw.add_watch(tmpdir)
            watched = fw.get_watched_dirs()
            assert tmpdir in watched

    def test_remove_watch(self):
        bus = EventBus()
        fw = FileWatcher(bus, directories=[])

        with tempfile.TemporaryDirectory() as tmpdir:
            fw.add_watch(tmpdir)
            assert tmpdir in fw.get_watched_dirs()
            result = fw.remove_watch(tmpdir)
            assert result is True
            assert tmpdir not in fw.get_watched_dirs()

    def test_remove_nonexistent_watch_returns_false(self):
        bus = EventBus()
        fw = FileWatcher(bus, directories=[])
        result = fw.remove_watch("/nonexistent/path")
        assert result is False

    def test_detects_created_file(self):
        bus = EventBus()
        fw = FileWatcher(bus, interval=0.5, directories=[])

        with tempfile.TemporaryDirectory() as tmpdir:
            fw.add_watch(tmpdir)
            fw.start()
            time.sleep(0.3)

            # Create a file
            test_file = os.path.join(tmpdir, "test_create.txt")
            with open(test_file, "w") as f:
                f.write("hello")

            time.sleep(0.8)

            changes = fw.get_recent_changes()
            created = [c for c in changes if c["event"] == "fs.file.created"]
            assert any(test_file in c["path"] for c in created), f"Created file not detected. Changes: {changes}"
            fw.stop()

    def test_detects_modified_file(self):
        bus = EventBus()
        fw = FileWatcher(bus, interval=0.5, directories=[])

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "test_mod.txt")
            with open(test_file, "w") as f:
                f.write("original")
            # Ensure a distinct mtime
            time.sleep(0.1)

            fw.add_watch(tmpdir)
            fw.start()
            time.sleep(0.8)

            # Modify the file — wait to ensure mtime changes
            time.sleep(0.1)
            with open(test_file, "w") as f:
                f.write("modified")

            time.sleep(1.0)

            changes = fw.get_recent_changes()
            modified = [c for c in changes if c["event"] == "fs.file.modified"]
            assert any(test_file in c["path"] for c in modified), f"Modified file not detected. Changes: {changes}"
            fw.stop()

    def test_detects_deleted_file(self):
        bus = EventBus()
        fw = FileWatcher(bus, interval=0.5, directories=[])

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "test_del.txt")
            with open(test_file, "w") as f:
                f.write("delete me")

            fw.add_watch(tmpdir)
            fw.start()
            time.sleep(0.5)

            # Delete the file
            os.unlink(test_file)

            time.sleep(0.8)

            changes = fw.get_recent_changes()
            deleted = [c for c in changes if c["event"] == "fs.file.deleted"]
            assert any(test_file in c["path"] for c in deleted), f"Deleted file not detected. Changes: {changes}"
            fw.stop()

    def test_emits_correct_event_types(self):
        bus = EventBus()
        fw = FileWatcher(bus, interval=0.5, directories=[])
        received = []

        def handler(et, data):
            received.append(et)

        bus.subscribe("fs.file.created", handler)
        bus.subscribe("fs.file.modified", handler)
        bus.subscribe("fs.file.deleted", handler)

        with tempfile.TemporaryDirectory() as tmpdir:
            fw.add_watch(tmpdir)
            fw.start()
            time.sleep(0.3)

            test_file = os.path.join(tmpdir, "event_test.txt")
            with open(test_file, "w") as f:
                f.write("test")

            time.sleep(0.8)

            assert "fs.file.created" in received
            fw.stop()

    def test_get_recent_changes_returns_events(self):
        bus = EventBus()
        fw = FileWatcher(bus, interval=0.5, directories=[])

        with tempfile.TemporaryDirectory() as tmpdir:
            fw.add_watch(tmpdir)
            fw.start()
            time.sleep(0.3)

            test_file = os.path.join(tmpdir, "recent_test.txt")
            with open(test_file, "w") as f:
                f.write("test")

            time.sleep(0.8)

            changes = fw.get_recent_changes()
            assert len(changes) >= 1
            assert "event" in changes[0]
            assert "path" in changes[0]
            assert "timestamp" in changes[0]
            fw.stop()

    def test_stops_cleanly(self):
        bus = EventBus()
        fw = FileWatcher(bus)
        fw.start()
        fw.stop()
        assert fw.is_running is False

    def test_get_watched_dirs_includes_defaults(self):
        bus = EventBus()
        fw = FileWatcher(bus)
        dirs = fw.get_watched_dirs()
        assert len(dirs) >= 2
        assert any("Downloads" in d for d in dirs)
        assert any("ai-dos" in d for d in dirs)
