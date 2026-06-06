"""
AI-DOS Kernel: Event Bus
In-process pub/sub event system with segment-aware wildcard support.
"""

from typing import Any, Callable


EventHandler = Callable[..., Any]


def _match_segments(pattern: str, event_type: str) -> bool:
    """Segment-aware pattern matching.

    Both *pattern* and *event_type* are split by ``.``.
    ``*`` matches exactly one segment (any characters except ``.``).
    All other characters match literally.

    Examples::

        _match_segments("task.*", "task.completed")       → True
        _match_segments("task.*", "task.completed.details") → False
        _match_segments("service.*.heartbeat", "service.foo.heartbeat") → True
    """
    pat_parts = pattern.split(".")
    evt_parts = event_type.split(".")

    if len(pat_parts) != len(evt_parts):
        return False

    for pat, evt in zip(pat_parts, evt_parts):
        if pat == "*":
            continue
        if pat != evt:
            return False

    return True


class EventBus:
    """
    Lightweight in-process pub/sub event bus.

    Subscribers register for event types by dotted pattern.
    ``*`` matches exactly one segment (no dot crossing).

    Handlers receive ``(event_type, data)`` when a matching event is emitted.
    """

    def __init__(self):
        self._subscribers: dict[str, list[EventHandler]] = {}

    def subscribe(self, event_type: str, handler: EventHandler):
        """Register *handler* for *event_type*.  ``*`` matches one segment."""
        self._subscribers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler):
        """Remove *handler* from *event_type*.  No-op if not subscribed."""
        handlers = self._subscribers.get(event_type)
        if handlers is not None:
            try:
                handlers.remove(handler)
            except ValueError:
                pass

    def emit(self, event_type: str, data: Any = None):
        """Emit *event_type* with *data* to all matching subscribers.

        A handler exception never propagates — other handlers still run.
        """
        for pattern, handlers in list(self._subscribers.items()):
            if not _match_segments(pattern, event_type):
                continue
            for handler in list(handlers):
                try:
                    handler(event_type, data)
                except Exception:
                    pass

    def clear(self):
        """Remove all subscribers."""
        self._subscribers.clear()
