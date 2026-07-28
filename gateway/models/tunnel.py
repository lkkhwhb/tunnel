"""
TunnelConnection model.

Represents an active WebSocket tunnel connection from a client SDK.
Encapsulates the WebSocket handle, connection metadata, and per-tunnel
statistics with thread-safe send operations.
"""

import time
import threading

from gateway.utils.log import get_logger

logger = get_logger()


class TunnelConnection:
    """
    A single registered tunnel connection.

    Encapsulates the raw WebSocket reference, a per-connection send lock
    for thread-safe message delivery, connection timestamps, and per-tunnel
    traffic / request statistics.

    Thread-safety
    -------------
    * ``send()`` acquires the internal *send_lock* so that heartbeat pings
      and proxy request frames never interleave.
    * Statistic counters (``bytes_uploaded``, ``bytes_downloaded``, etc.)
      are mutated from a single logical owner at a time (upload from the
      proxy thread, download from the multiplexer thread) and are therefore
      safe under the CPython GIL.  This mirrors the original single-file
      design.
    """

    __slots__ = (
        "ws",
        "client_ip",
        "send_lock",
        "connected_at",
        "last_active",
        "requests_served",
        "bytes_uploaded",
        "bytes_downloaded",
    )

    def __init__(self, ws, client_ip: str):
        self.ws = ws
        self.client_ip = client_ip
        self.send_lock = threading.Lock()
        self.connected_at = time.time()
        self.last_active = time.time()
        self.requests_served: int = 0
        self.bytes_uploaded: int = 0
        self.bytes_downloaded: int = 0

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    def send(self, message: str) -> None:
        """
        Send a JSON string through the WebSocket, acquiring the send lock.

        This ensures that concurrent senders (heartbeat worker, proxy
        threads) never produce interleaved WebSocket frames.

        Args:
            message: A pre-serialized JSON string.
        """
        with self.send_lock:
            self.ws.send(message)

    # ------------------------------------------------------------------
    # Lifecycle Helpers
    # ------------------------------------------------------------------

    def touch(self) -> None:
        """Update the *last_active* timestamp to reflect recent activity."""
        self.last_active = time.time()

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def record_upload(self, byte_count: int) -> None:
        """Record bytes sent from the proxy to this tunnel client."""
        self.bytes_uploaded += byte_count

    def record_download(self, byte_count: int) -> None:
        """Record bytes received from this tunnel client."""
        self.bytes_downloaded += byte_count

    def increment_requests(self) -> None:
        """Increment the per-tunnel served-request counter."""
        self.requests_served += 1

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_info_dict(self) -> dict:
        """
        Serialize tunnel metadata for admin API responses.

        Returns:
            dict with keys: *client_ip*, *uptime_seconds*,
            *requests_served*, *bytes_uploaded*, *bytes_downloaded*,
            *total_bytes_transferred*.
        """
        return {
            "client_ip": self.client_ip,
            "uptime_seconds": round(time.time() - self.connected_at, 2),
            "requests_served": self.requests_served,
            "bytes_uploaded": self.bytes_uploaded,
            "bytes_downloaded": self.bytes_downloaded,
            "total_bytes_transferred": self.bytes_uploaded + self.bytes_downloaded,
        }
