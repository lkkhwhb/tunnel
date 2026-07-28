"""
HeartbeatService.

Background daemon thread that periodically pings connected tunnel clients
and reaps connections that have gone silent beyond the configured timeout.
"""

import time
import threading

from gateway.config.settings import PING_INTERVAL, PING_TIMEOUT
from gateway.protocol.messages import build_ping
from gateway.utils.log import get_logger

logger = get_logger()


class HeartbeatService:
    """
    Monitors tunnel connections via periodic WebSocket pings.

    The worker thread:
    1. Sleeps for ``PING_INTERVAL`` seconds.
    2. Takes a snapshot of active tunnels (releases the manager lock).
    3. For each tunnel, checks the inactivity window.  If the tunnel
       exceeds ``PING_TIMEOUT``, it is marked for removal.  Otherwise
       a ``{"type": "ping"}`` message is sent.
    4. Dead tunnels are reaped in a single batch removal.
    """

    def __init__(self, tunnel_manager):
        """
        Args:
            tunnel_manager: The :class:`TunnelManager` to monitor.
        """
        self._tunnel_manager = tunnel_manager
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Spawn the heartbeat daemon thread."""
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        logger.info(
            f"Heartbeat service started "
            f"(interval={PING_INTERVAL}s, timeout={PING_TIMEOUT}s)"
        )

    def _worker(self) -> None:
        """Background loop: ping clients and reap dead connections."""
        ping_message = build_ping()

        while True:
            time.sleep(PING_INTERVAL)
            now = time.time()
            dead_tunnels: list[str] = []

            # Take a snapshot to avoid holding the lock during network I/O
            tunnels_snapshot = self._tunnel_manager.snapshot()

            for path, tunnel in tunnels_snapshot:
                if now - tunnel.last_active > PING_TIMEOUT:
                    logger.warning(
                        f"Tunnel {path} timed out (no heartbeat/activity)."
                    )
                    dead_tunnels.append(path)
                else:
                    try:
                        tunnel.send(ping_message)
                    except Exception as e:
                        logger.warning(f"Heartbeat ping failed for {path}: {e}")
                        dead_tunnels.append(path)

            if dead_tunnels:
                self._tunnel_manager.remove_many(dead_tunnels)
