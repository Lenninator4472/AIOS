"""Tests for kernel/service.py — Service base class."""

import pytest
from kernel.bus import EventBus
from kernel.service import Service


class TestService:
    """Service: lifecycle, health checks, event integration."""

    def test_service_has_name(self):
        """Service should store its name."""
        bus = EventBus()
        svc = Service("test_svc", bus)
        assert svc.name == "test_svc"

    def test_service_starts_not_running(self):
        """Service should start in non-running state."""
        bus = EventBus()
        svc = Service("test_svc", bus)
        assert svc.is_running is False

    def test_start_sets_running(self):
        """After start(), is_running should be True."""
        bus = EventBus()
        svc = Service("test_svc", bus)
        svc.start()
        assert svc.is_running is True

    def test_stop_clears_running(self):
        """After stop(), is_running should be False."""
        bus = EventBus()
        svc = Service("test_svc", bus)
        svc.start()
        svc.stop()
        assert svc.is_running is False

    def test_start_emits_service_started_event(self):
        """start() should emit 'service.<name>.started'."""
        bus = EventBus()
        svc = Service("test_svc", bus)
        received = []

        def handler(et, data):
            received.append((et, data))

        bus.subscribe("service.test_svc.started", handler)
        svc.start()

        assert len(received) == 1
        assert received[0][0] == "service.test_svc.started"

    def test_stop_emits_service_stopped_event(self):
        """stop() should emit 'service.<name>.stopped'."""
        bus = EventBus()
        svc = Service("test_svc", bus)
        received = []

        def handler(et, data):
            received.append(et)

        bus.subscribe("service.test_svc.stopped", handler)
        svc.start()
        svc.stop()

        assert len(received) == 1
        assert received[0] == "service.test_svc.stopped"

    def test_health_check_returns_running_status(self):
        """health_check() should return dict with name and running."""
        bus = EventBus()
        svc = Service("test_svc", bus)
        svc.start()

        status = svc.health_check()

        assert isinstance(status, dict)
        assert status["name"] == "test_svc"
        assert status["running"] is True

    def test_health_check_when_stopped(self):
        """health_check() should reflect stopped state."""
        bus = EventBus()
        svc = Service("test_svc", bus)
        status = svc.health_check()

        assert status["running"] is False

    def test_double_start_is_idempotent(self):
        """Calling start() twice should not raise."""
        bus = EventBus()
        svc = Service("test_svc", bus)
        svc.start()
        svc.start()  # should not raise
        assert svc.is_running is True

    def test_double_stop_is_idempotent(self):
        """Calling stop() when not running should not raise."""
        bus = EventBus()
        svc = Service("test_svc", bus)
        svc.stop()  # should not raise
        assert svc.is_running is False

    def test_subclass_can_override_on_start(self):
        """Subclasses can override _on_start() for custom init logic."""
        bus = EventBus()
        started = False

        class CustomService(Service):
            def _on_start(self):
                nonlocal started
                started = True

        svc = CustomService("custom", bus)
        svc.start()

        assert started is True

    def test_subclass_can_override_on_stop(self):
        """Subclasses can override _on_stop() for custom cleanup."""
        bus = EventBus()
        cleaned = False

        class CustomService(Service):
            def _on_stop(self):
                nonlocal cleaned
                cleaned = True

        svc = CustomService("custom", bus)
        svc.start()
        svc.stop()

        assert cleaned is True

    def test_health_check_includes_custom_data(self):
        """Subclasses can extend health_check() with custom fields."""
        bus = EventBus()

        class MonitoredService(Service):
            def health_check(self):
                info = super().health_check()
                info["tasks_completed"] = 42
                return info

        svc = MonitoredService("monitored", bus)
        status = svc.health_check()

        assert status["tasks_completed"] == 42

    def test_wildcard_subscription_works(self):
        """Wildcard 'service.*.started' should match any service start."""
        bus = EventBus()
        received = []

        def handler(et, data):
            received.append(et)

        bus.subscribe("service.*.started", handler)
        svc1 = Service("svc1", bus)
        svc2 = Service("svc2", bus)
        svc1.start()
        svc2.start()

        assert len(received) == 2
