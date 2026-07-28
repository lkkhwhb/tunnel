"""
ServerStats model.

Thread-safe aggregate statistics for the tunnel gateway server.
Tracks request counts, byte transfers, and latency metrics.
"""

import threading
import time


class ServerStats:
    """
    Thread-safe container for server-wide aggregate statistics.

    Every mutation method acquires an internal lock to ensure consistency
    across concurrent request-processing threads.

    Design note
    -----------
    The original codebase used a plain ``dict`` with a separate
    ``threading.Lock``.  This class encapsulates both, exposing atomic
    operations and a ``snapshot()`` method that reads all values under
    a single lock acquisition.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.started_at: float = time.time()
        self.total_requests: int = 0
        self.active_requests: int = 0
        self.bytes_uploaded: int = 0
        self.bytes_downloaded: int = 0
        self.total_latency_ms: float = 0.0

    # ------------------------------------------------------------------
    # Request Lifecycle
    # ------------------------------------------------------------------

    def record_request_start(self) -> None:
        """Increment total and active request counters atomically."""
        with self._lock:
            self.total_requests += 1
            self.active_requests += 1

    def record_request_end(self, latency_ms: float) -> None:
        """
        Decrement active requests and accumulate latency.

        Args:
            latency_ms: The request duration in milliseconds.
        """
        with self._lock:
            self.active_requests = max(0, self.active_requests - 1)
            self.total_latency_ms += latency_ms

    # ------------------------------------------------------------------
    # Byte Counters
    # ------------------------------------------------------------------

    def record_upload(self, byte_count: int) -> None:
        """Record bytes sent from the proxy to tunnel clients."""
        with self._lock:
            self.bytes_uploaded += byte_count

    def record_download(self, byte_count: int) -> None:
        """Record bytes received from tunnel clients."""
        with self._lock:
            self.bytes_downloaded += byte_count

    def reset(self) -> None:
        """Reset all request counters and byte metrics atomically."""
        with self._lock:
            self.total_requests = 0
            self.active_requests = 0
            self.bytes_uploaded = 0
            self.bytes_downloaded = 0
            self.total_latency_ms = 0.0

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """
        Return a consistent point-in-time snapshot of all statistics.

        All values are read under one lock acquisition so callers get
        a self-consistent view (e.g. ``total_requests`` and
        ``total_latency_ms`` are from the same instant).

        Returns:
            dict with keys: *started_at*, *uptime_seconds*,
            *total_requests*, *active_requests*, *bytes_uploaded*,
            *bytes_downloaded*, *total_bytes_transferred*,
            *average_latency_ms*.
        """
        with self._lock:
            uptime = time.time() - self.started_at
            total = self.total_requests
            active = self.active_requests
            up = self.bytes_uploaded
            down = self.bytes_downloaded
            lat = self.total_latency_ms

        avg_latency = round(lat / total, 2) if total > 0 else 0.0

        return {
            "started_at": self.started_at,
            "uptime_seconds": round(uptime, 2),
            "total_requests": total,
            "active_requests": active,
            "bytes_uploaded": up,
            "bytes_downloaded": down,
            "total_bytes_transferred": up + down,
            "average_latency_ms": avg_latency,
        }
