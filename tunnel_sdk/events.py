"""
Event emitter for SDK callbacks.
"""
from typing import Callable, Dict, List, Any

class EventEmitter:
    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}

    def on(self, event: str, callback: Callable) -> None:
        """Register a callback for an event."""
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)

    def off(self, event: str, callback: Callable) -> None:
        """Unregister a callback for an event."""
        if event in self._listeners:
            try:
                self._listeners[event].remove(callback)
            except ValueError:
                pass

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Emit an event, calling all registered callbacks synchronously."""
        for callback in self._listeners.get(event, []):
            try:
                callback(*args, **kwargs)
            except Exception:
                # User callbacks shouldn't crash the SDK loop
                pass
