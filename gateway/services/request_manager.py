"""
RequestManager service.

Thread-safe registry for in-flight proxied requests.  Maps request IDs
to their :class:`~gateway.models.request.RequestState` objects.

Includes a background TTL reaper that removes orphaned requests to
prevent memory leaks when a tunnel disconnects mid-request.
"""

import threading
import time

from gateway.models.request import RequestState
from gateway.utils.metrics import ACTIVE_REQUESTS
from gateway.utils.log import get_logger

logger = get_logger(__name__)

# Orphaned requests older than this are reaped (seconds).
_REQUEST_TTL = 120
# How often the reaper thread runs (seconds).
_REAP_INTERVAL = 30


class RequestManager:
    """
    Manages the lifecycle of pending proxied HTTP requests.

    All operations are thread-safe through an internal lock.
    A background reaper thread removes stale entries to prevent
    memory leaks from orphaned requests.
    """

    def __init__(self):
        self._requests: dict[str, RequestState] = {}
        self._lock = threading.Lock()
        self._start_reaper()

    # ------------------------------------------------------------------
    # Reaper
    # ------------------------------------------------------------------

    def _start_reaper(self) -> None:
        """Spawn a daemon thread that periodically removes orphaned requests."""
        t = threading.Thread(target=self._reaper_loop, daemon=True)
        t.start()

    def _reaper_loop(self) -> None:
        """Background loop that removes requests older than _REQUEST_TTL."""
        while True:
            time.sleep(_REAP_INTERVAL)
            self._reap_stale()

    def _reap_stale(self) -> None:
        """Remove all requests whose start_time is older than _REQUEST_TTL."""
        cutoff = time.time() - _REQUEST_TTL
        with self._lock:
            stale = [
                rid for rid, state in self._requests.items()
                if state.start_time < cutoff
            ]
            for rid in stale:
                del self._requests[rid]
                ACTIVE_REQUESTS.dec()
        if stale:
            logger.info(
                "stale_requests_reaped",
                extra={"count": len(stale)},
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
            ACTIVE_REQUESTS.inc()
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
            if req_id in self._requests:
                del self._requests[req_id]
                ACTIVE_REQUESTS.dec()

    def pending_count(self) -> int:
        """Return the number of currently pending requests."""
        with self._lock:
            return len(self._requests)
