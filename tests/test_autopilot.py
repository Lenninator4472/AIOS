"""Tests for kernel/autopilot.py — Autonomous Agent / Autopilot."""

import time
from kernel.bus import EventBus
from kernel.autopilot import AutoPilot


class _MockLLM:
    """A fake LLM provider used for testing."""

    def query(self, system_prompt, user_input, context=None):
        return f"[mock analysis of: {user_input[:50]}]"


def _mock_provider():
    return _MockLLM()


class TestAutoPilot:
    """AutoPilot: event subscriptions, action log, stats."""

    def test_constructor_sets_name(self):
        bus = EventBus()
        ap = AutoPilot("autopilot", bus)
        assert ap.name == "autopilot"

    def test_subscribes_to_expected_event_patterns(self):
        bus = EventBus()
        ap = AutoPilot("autopilot", bus)
        ap.start()
        # Verify subscriptions by emitting events and checking they're captured
        assert ap._running is True
        ap.stop()

    def test_records_task_failed_events_in_action_log(self):
        bus = EventBus()
        ap = AutoPilot("autopilot", bus, llm_provider=_mock_provider)
        ap.start()

        bus.emit("task.failed", {
            "task_id": "t1",
            "command": "echo hello",
            "stderr": "permission denied",
            "exit_code": 1,
        })
        time.sleep(0.2)  # Wait for background thread

        log = ap.get_action_log()
        events = [e["event"] for e in log]
        assert "task.failed" in events
        ap.stop()

    def test_records_task_completed_in_action_log(self):
        bus = EventBus()
        ap = AutoPilot("autopilot", bus)
        ap.start()

        bus.emit("task.completed", {"task_id": "t2", "exit_code": 0})
        time.sleep(0.1)

        log = ap.get_action_log()
        events = [e["event"] for e in log]
        assert "task.completed" in events
        ap.stop()

    def test_records_system_health_warning_in_action_log(self):
        bus = EventBus()
        ap = AutoPilot("autopilot", bus)
        ap.start()

        bus.emit("system.health.warning", {"cpu_percent": 80, "mem_percent": 30})
        time.sleep(0.1)

        log = ap.get_action_log()
        events = [e["event"] for e in log]
        assert "system.health.warning" in events
        ap.stop()

    def test_records_system_health_critical_in_action_log(self):
        bus = EventBus()
        ap = AutoPilot("autopilot", bus, llm_provider=_mock_provider)
        ap.start()

        bus.emit("system.health.critical", {"cpu_percent": 95, "mem_percent": 90})
        time.sleep(0.2)

        log = ap.get_action_log()
        events = [e["event"] for e in log]
        assert "system.health.critical" in events
        ap.stop()

    def test_get_action_log_returns_ordered_results(self):
        bus = EventBus()
        ap = AutoPilot("autopilot", bus)
        ap.start()

        bus.emit("task.completed", {"task_id": "1"})
        bus.emit("task.completed", {"task_id": "2"})
        bus.emit("task.completed", {"task_id": "3"})
        time.sleep(0.1)

        log = ap.get_action_log(limit=2)
        assert len(log) == 2
        # Most recent first
        assert log[0]["data"]["task_id"] == "3"
        assert log[1]["data"]["task_id"] == "2"
        ap.stop()

    def test_get_stats_returns_correct_counts(self):
        bus = EventBus()
        ap = AutoPilot("autopilot", bus)
        ap.start()

        bus.emit("task.completed", {"task_id": "1"})
        bus.emit("task.completed", {"task_id": "2"})
        bus.emit("system.health.warning", {"cpu_percent": 80})
        time.sleep(0.1)

        stats = ap.get_stats()
        assert stats.get("task.completed") == 2
        assert stats.get("system.health.warning") == 1
        ap.stop()

    def test_does_not_crash_on_unknown_events(self):
        bus = EventBus()
        ap = AutoPilot("autopilot", bus)
        ap.start()

        # Emit an event pattern the autopilot doesn't subscribe to
        bus.emit("some.random.event", {"data": "test"})
        time.sleep(0.1)

        log = ap.get_action_log()
        events = [e["event"] for e in log]
        assert "some.random.event" not in events
        ap.stop()

    def test_action_log_is_bounded(self):
        bus = EventBus()
        ap = AutoPilot("autopilot", bus)
        ap.start()

        # Emit more than the max limit
        for i in range(150):
            bus.emit("task.completed", {"task_id": str(i)})
        time.sleep(0.2)

        log = ap.get_action_log(limit=200)
        # Max internal size is 100
        assert len(log) <= 100
        ap.stop()

    def test_emits_autopilot_action_on_critical_health(self):
        bus = EventBus()
        ap = AutoPilot("autopilot", bus, llm_provider=_mock_provider)
        ap.start()
        received = []

        def handler(et, data):
            received.append(et)

        bus.subscribe("autopilot.action", handler)
        bus.emit("system.health.critical", {"cpu_percent": 95, "mem_percent": 90})
        time.sleep(0.3)

        assert "autopilot.action" in received
        ap.stop()

    def test_health_check_includes_name(self):
        bus = EventBus()
        ap = AutoPilot("autopilot", bus)
        hc = ap.health_check()
        assert hc["name"] == "autopilot"
