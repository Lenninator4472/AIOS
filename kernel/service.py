"""
AI-DOS Kernel: Service Abstraction
Base class for system services/daemons with lifecycle management.
"""

from kernel.bus import EventBus


class Service:
    """
    Base class for AI-OS services.

    Manages lifecycle (start/stop), emits lifecycle events on the EventBus,
    and provides a standard health_check() interface.

    Subclasses override :meth:`_on_start` and :meth:`_on_stop` for custom
    initialization and cleanup.
    """

    def __init__(self, name: str, bus: EventBus):
        self._name = name
        self._bus = bus
        self._running = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self):
        """Start the service. Idempotent — safe to call multiple times."""
        if self._running:
            return
        self._running = True
        self._on_start()
        self._bus.emit(f"service.{self._name}.started", {"name": self._name})

    def stop(self):
        """Stop the service. Idempotent — safe to call multiple times."""
        if not self._running:
            return
        self._running = False
        self._on_stop()
        self._bus.emit(f"service.{self._name}.stopped", {"name": self._name})

    def health_check(self) -> dict:
        """Return a dict with current health status.

        Subclasses should extend this with additional metrics.
        """
        return {"name": self._name, "running": self._running}

    def _on_start(self):
        """Hook for subclass initialization. Called during start()."""

    def _on_stop(self):
        """Hook for subclass cleanup. Called during stop()."""
