"""
RequestManager service.

Thread-safe registry for in-flight proxied requests.  Maps request IDs
to their :class:`~gateway.models.request.RequestState` objects.
"""

import threading

from gateway.models.request import RequestState
from gateway.utils.log import get_logger

logger = get_logger()


class RequestManager:
    """
    Manages the lifecycle of pending proxied HTTP requests.

    All operations are thread-safe through an internal lock.
    """

    def __init__(self):
        self._requests: dict[str, RequestState] = {}
        self._lock = threading.Lock()

    def create(self, req_id: str, start_time: float) -> RequestState:
        """
        Create and register a new :class:`RequestState`.

        Args:
            req_id:     Unique request identifier (UUID).
            start_time: The ``time.time()`` when the request arrived.

        Returns:
            The newly created request state.
        """
        state = RequestState(req_id, start_time)
        with self._lock:
            self._requests[req_id] = state
        return state

    def get(self, req_id: str) -> RequestState | None:
        """
        Retrieve a pending request by its ID.

        Args:
            req_id: The request identifier.

        Returns:
            The matching :class:`RequestState`, or ``None``.
        """
        with self._lock:
            return self._requests.get(req_id)

    def remove(self, req_id: str) -> None:
        """
        Remove a completed or timed-out request from the registry.

        Args:
            req_id: The request identifier to remove.
        """
        with self._lock:
            self._requests.pop(req_id, None)
