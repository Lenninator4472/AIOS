"""Tests for kernel/logger.py — Structured JSON Logging Service."""

import json
import os
import tempfile
import time

from kernel.bus import EventBus
from kernel.logger import LoggingService


class TestLoggingService:
    """LoggingService: event capture, file writing, query, rotation."""

    def test_constructor_sets_name(self):
        bus = EventBus()
        log = LoggingService(bus)
        assert log.name == "logger"

    def test_is_a_service(self):
        bus = EventBus()
        log = LoggingService(bus)
        assert hasattr(log, "start")
        assert hasattr(log, "stop")
        assert hasattr(log, "health_check")

    def test_captures_events_and_writes_to_log_file(self):
        bus = EventBus()
        with tempfile.TemporaryDirectory() as tmpdir:
            log = LoggingService(bus, log_dir=tmpdir)
            log.start()
            time.sleep(0.1)

            bus.emit("task.completed", {"task_id": "t1", "exit_code": 0})
            time.sleep(0.1)
            log.flush()

            log_path = log.get_log_path()
            assert os.path.exists(log_path)

            with open(log_path, "r") as f:
                content = f.read()
            assert "task.completed" in content
            assert "t1" in content
            log.stop()

    def test_log_file_is_valid_json_lines(self):
        bus = EventBus()
        with tempfile.TemporaryDirectory() as tmpdir:
            log = LoggingService(bus, log_dir=tmpdir)
            log.start()
            time.sleep(0.1)

            bus.emit("task.started", {"task_id": "t1"})
            bus.emit("task.completed", {"task_id": "t1"})
            time.sleep(0.1)
            log.flush()

            log_path = log.get_log_path()
            with open(log_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    assert "timestamp" in entry
                    assert "event" in entry
                    assert "data" in entry
            log.stop()

    def test_query_returns_matching_events(self):
        bus = EventBus()
        with tempfile.TemporaryDirectory() as tmpdir:
            log = LoggingService(bus, log_dir=tmpdir)
            log.start()
            time.sleep(0.1)

            bus.emit("task.started", {"task_id": "1"})
            bus.emit("task.completed", {"task_id": "1"})
            bus.emit("system.health.ok", {"cpu": 10})
            time.sleep(0.1)
            log.flush()

            results = log.query(limit=10)
            assert len(results) >= 3
            log.stop()

    def test_query_with_event_type_filters_correctly(self):
        bus = EventBus()
        with tempfile.TemporaryDirectory() as tmpdir:
            log = LoggingService(bus, log_dir=tmpdir)
            log.start()
            time.sleep(0.1)

            bus.emit("task.started", {"task_id": "1"})
            bus.emit("task.completed", {"task_id": "1"})
            bus.emit("system.health.ok", {"cpu": 10})
            bus.emit("task.failed", {"task_id": "2"})
            time.sleep(0.1)
            log.flush()

            task_events = log.query(event_type="task.failed", limit=10)
            assert len(task_events) >= 1
            for e in task_events:
                assert e["event"] == "task.failed"
            log.stop()

    def test_get_log_path_returns_string_path(self):
        bus = EventBus()
        with tempfile.TemporaryDirectory() as tmpdir:
            log = LoggingService(bus, log_dir=tmpdir)
            log.start()
            path = log.get_log_path()
            assert isinstance(path, str)
            assert path.startswith(tmpdir)
            assert path.endswith(".jsonl")
            log.stop()

    def test_stops_cleanly(self):
        bus = EventBus()
        with tempfile.TemporaryDirectory() as tmpdir:
            log = LoggingService(bus, log_dir=tmpdir)
            log.start()
            log.stop()
            assert log.is_running is False

    def test_query_on_empty_log(self):
        bus = EventBus()
        with tempfile.TemporaryDirectory() as tmpdir:
            log = LoggingService(bus, log_dir=tmpdir)
            # Query before starting — no log file exists yet
            log.start()
            log.flush()
            # After start, service.started event is logged — query for something else
            results = log.query(event_type="nonexistent.event", limit=10)
            assert results == []
            log.stop()

    def test_flush_does_not_crash(self):
        bus = EventBus()
        with tempfile.TemporaryDirectory() as tmpdir:
            log = LoggingService(bus, log_dir=tmpdir)
            log.start()
            bus.emit("test.event", {"msg": "hello"})
            time.sleep(0.1)
            # flush should be safe
            log.flush()
            # flush again should be safe
            log.flush()
            log.stop()
            # flush after stop should be safe
            log.flush()
