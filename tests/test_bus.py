"""Tests for kernel/bus.py — EventBus pub/sub system."""

import pytest
from kernel.bus import EventBus


class TestEventBus:
    """EventBus: core pub/sub with wildcard support."""

    def test_subscribe_and_emit(self):
        """Subscriber should be called when matching event is emitted."""
        bus = EventBus()
        received = []

        def handler(event_type, data):
            received.append(data)

        bus.subscribe("test.event", handler)
        bus.emit("test.event", {"msg": "hello"})

        assert len(received) == 1
        assert received[0] == {"msg": "hello"}

    def test_multiple_subscribers_same_event(self):
        """Multiple subscribers on same event all get called."""
        bus = EventBus()
        results = []

        def handler1(et, data):
            results.append("h1")

        def handler2(et, data):
            results.append("h2")

        bus.subscribe("evt", handler1)
        bus.subscribe("evt", handler2)
        bus.emit("evt", {})

        assert len(results) == 2
        assert "h1" in results
        assert "h2" in results

    def test_unsubscribe(self):
        """Unsubscribed handler should not be called."""
        bus = EventBus()
        received = []

        def handler(et, data):
            received.append(data)

        bus.subscribe("test.event", handler)
        bus.unsubscribe("test.event", handler)
        bus.emit("test.event", {"x": 1})

        assert len(received) == 0

    def test_no_matching_subscriber(self):
        """Emit with no subscribers should not raise."""
        bus = EventBus()
        bus.emit("nonexistent.event", {})  # should not raise

    def test_emit_with_no_data(self):
        """Emit without data should work (default None)."""
        bus = EventBus()
        received = []

        def handler(et, data):
            received.append(data)

        bus.subscribe("evt", handler)
        bus.emit("evt")

        assert len(received) == 1
        assert received[0] is None

    def test_wildcard_exact_match(self):
        """Literal pattern 'task.completed' should match 'task.completed'."""
        bus = EventBus()
        received = []

        def handler(et, data):
            received.append(et)

        bus.subscribe("task.completed", handler)
        bus.emit("task.completed", {})

        assert len(received) == 1
        assert received[0] == "task.completed"

    def test_wildcard_matches_any_suffix(self):
        """Pattern 'task.*' should match 'task.completed', 'task.failed', etc."""
        bus = EventBus()
        received = []

        def handler(et, data):
            received.append(et)

        bus.subscribe("task.*", handler)
        bus.emit("task.completed", {"id": 1})
        bus.emit("task.failed", {"id": 2})
        bus.emit("task.started", {"id": 3})

        assert len(received) == 3
        assert "task.completed" in received
        assert "task.failed" in received
        assert "task.started" in received

    def test_wildcard_does_not_match_wrong_prefix(self):
        """Pattern 'task.*' should NOT match 'other.event'."""
        bus = EventBus()
        received = []

        def handler(et, data):
            received.append(et)

        bus.subscribe("task.*", handler)
        bus.emit("other.event", {})

        assert len(received) == 0

    def test_wildcard_matches_nested(self):
        """Pattern 'service.*.heartbeat' should match 'service.scheduler.heartbeat'."""
        bus = EventBus()
        received = []

        def handler(et, data):
            received.append(et)

        bus.subscribe("service.*.heartbeat", handler)
        bus.emit("service.scheduler.heartbeat", {})
        bus.emit("service.watcher.heartbeat", {})

        assert len(received) == 2

    def test_wildcard_does_not_match_partial(self):
        """Pattern 'task.*' should NOT match 'task.completed.details' (segment boundary via *)."""
        bus = EventBus()
        received = []

        def handler(et, data):
            received.append(et)

        bus.subscribe("task.*", handler)
        bus.emit("task.completed.details", {})

        assert len(received) == 0

    def test_subscribe_twice_same_handler(self):
        """Same handler subscribed twice should be called twice per emit."""
        bus = EventBus()
        count = 0

        def handler(et, data):
            nonlocal count
            count += 1

        bus.subscribe("evt", handler)
        bus.subscribe("evt", handler)
        bus.emit("evt", {})

        assert count == 2

    def test_error_in_handler_does_not_crash_bus(self):
        """If one handler raises, other handlers should still run."""
        bus = EventBus()
        results = []

        def bad_handler(et, data):
            raise ValueError("oops")

        def good_handler(et, data):
            results.append("ok")

        bus.subscribe("evt", bad_handler)
        bus.subscribe("evt", good_handler)
        bus.emit("evt", {})

        assert results == ["ok"]

    def test_unsubscribe_nonexistent(self):
        """Unsubscribing a handler that was never added should not raise."""
        bus = EventBus()
        bus.unsubscribe("evt", lambda et, d: None)  # should not raise

    def test_subscribe_wildcard_then_remove(self):
        """Wildcard subscription can be removed."""
        bus = EventBus()
        received = []

        def handler(et, data):
            received.append(et)

        bus.subscribe("task.*", handler)
        bus.unsubscribe("task.*", handler)
        bus.emit("task.completed", {})

        assert len(received) == 0

    def test_multiple_wildcard_patterns(self):
        """Multiple wildcard patterns should each match independently."""
        bus = EventBus()
        all_events = []
        task_events = []

        def all_handler(et, data):
            all_events.append(et)

        def task_handler(et, data):
            task_events.append(et)

        bus.subscribe("*.completed", all_handler)
        bus.subscribe("task.*", task_handler)
        bus.emit("task.completed", {"id": 1})

        assert len(all_events) == 1
        assert len(task_events) == 1

    def test_handler_called_with_event_type(self):
        """Handlers should receive both event type and data."""
        bus = EventBus()
        received = []

        def handler(event_type, data):
            received.append((event_type, data))

        bus.subscribe("test.event", handler)
        bus.emit("test.event", {"key": "val"})

        assert len(received) == 1
        assert received[0] == ("test.event", {"key": "val"})

    def test_clear_all_subscribers(self):
        """Clearing all subscribers should stop all events."""
        bus = EventBus()
        received = []

        def handler(et, data):
            received.append(et)

        bus.subscribe("evt1", handler)
        bus.subscribe("evt2", handler)
        bus.clear()
        bus.emit("evt1", {})
        bus.emit("evt2", {})

        assert len(received) == 0

    def test_event_type_preserved_in_wildcard(self):
        """Wildcard subscribers should receive the actual event_type emitted."""
        bus = EventBus()
        received = []

        def handler(et, data):
            received.append(et)

        bus.subscribe("task.*", handler)
        bus.emit("task.completed", {})

        assert received[0] == "task.completed"  # not "task.*"

    def test_data_preserved_across_subscribers(self):
        """Emitted data should be passed to all subscribers unchanged."""
        bus = EventBus()
        results = []

        def handler1(et, data):
            results.append(data["key"])

        def handler2(et, data):
            results.append(data["key"])

        bus.subscribe("evt", handler1)
        bus.subscribe("evt", handler2)
        bus.emit("evt", {"key": "val"})

        assert results == ["val", "val"]
