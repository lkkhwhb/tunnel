"""
HeartbeatService.

Background daemon thread that periodically pings connected tunnel clients,
reaps connections that have gone silent beyond the configured timeout,
and cleans up expired path bans.
"""

import time
import threading

from gateway.config.settings import PING_INTERVAL, PING_TIMEOUT
from gateway.protocol.messages import build_ping
from gateway.utils.log import get_logger

logger = get_logger(__name__)


class HeartbeatService:
    """
    Monitors tunnel connections via periodic WebSocket pings.

    The worker thread:
    1. Sleeps for ``PING_INTERVAL`` seconds.
    2. Takes a snapshot of active tunnels (releases the manager lock).
    3. For each tunnel, checks the inactivity window.  Tunnels beyond
       ``PING_TIMEOUT`` are marked for removal; others receive a ping.
    4. Dead tunnels are reaped in a single batch removal.
    5. Expired path bans are cleaned up.
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
            "heartbeat_started",
            extra={"interval_s": PING_INTERVAL, "timeout_s": PING_TIMEOUT},
        )

    def _worker(self) -> None:
        """Background loop: ping clients, reap dead connections, clean bans."""
        ping_message = build_ping()

        while True:
            time.sleep(PING_INTERVAL)
            now = time.time()
            dead_tunnels: list[str] = []
            timed_out = 0
            ping_failed = 0

            # Take a snapshot to avoid holding the lock during network I/O
            tunnels_snapshot = self._tunnel_manager.snapshot()
            total = len(tunnels_snapshot)

            for path, tunnel in tunnels_snapshot:
                if now - tunnel.last_active > PING_TIMEOUT:
                    dead_tunnels.append(path)
                    timed_out += 1
                else:
                    try:
                        if getattr(tunnel, "dead", False):
                            dead_tunnels.append(path)
                            ping_failed += 1
                        else:
                            tunnel.send(ping_message)
                    except Exception:
                        dead_tunnels.append(path)
                        ping_failed += 1

            if dead_tunnels:
                self._tunnel_manager.remove_many(dead_tunnels)
                logger.warning(
                    "heartbeat_reap_summary",
                    extra={
                        "total_tunnels": total,
                        "timed_out": timed_out,
                        "ping_failed": ping_failed,
                    },
                )

            # Clean up expired path bans
            expired_bans = self._tunnel_manager.cleanup_expired_bans()
            if expired_bans:
                logger.info(
                    "expired_bans_cleaned",
                    extra={"count": expired_bans},
                )
