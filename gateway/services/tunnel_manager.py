"""
TunnelManager service.

Thread-safe registry for active WebSocket tunnel connections.
Handles registration, deregistration, longest-prefix matching,
path banning (force-disconnect protection), and provides snapshots
for admin reporting and heartbeat iteration.
"""

import threading
import time

from gateway.models.tunnel import TunnelConnection
from gateway.utils.metrics import ACTIVE_TUNNELS
from gateway.utils.log import get_logger

logger = get_logger(__name__)


class TunnelManager:
    """
    Manages the lifecycle of active tunnel connections.

    All public methods are thread-safe through an internal lock.  Methods
    that iterate over tunnels (``snapshot``, ``get_tunnels_info``) return
    copies so callers never hold the lock during slow operations such as
    network I/O.

    Ban mechanism
    -------------
    When an admin force-disconnects a tunnel, the path is temporarily
    banned to prevent the client's auto-reconnect from immediately
    re-registering.  Bans expire after a configurable duration.
    """

    def __init__(self):
        self._tunnels: dict[str, TunnelConnection] = {}
        self._banned_paths: dict[str, float] = {}  # path -> expiry timestamp
        self._lock = threading.Lock()
        # Pre-sorted path list for O(1) longest-prefix matching
        self._sorted_paths: list[str] = []

    # ------------------------------------------------------------------
    # Path Sorting (maintained on register/unregister)
    # ------------------------------------------------------------------

    def _rebuild_sorted_paths(self) -> None:
        """Rebuild the pre-sorted path list.  Must be called under lock."""
        self._sorted_paths = sorted(self._tunnels.keys(), key=len, reverse=True)

    # ------------------------------------------------------------------
    # Ban Mechanism
    # ------------------------------------------------------------------

    def ban(self, target_path: str, duration: float) -> None:
        """
        Ban a path from re-registration for *duration* seconds.

        Args:
            target_path: The tunnel path to ban.
            duration:    Ban duration in seconds.
        """
        with self._lock:
            self._banned_paths[target_path] = time.time() + duration
            logger.info(
                "path_banned",
                extra={"target_path": target_path, "duration_s": duration},
            )

    def unban(self, target_path: str) -> bool:
        """
        Remove a path ban.

        Returns:
            ``True`` if the path was banned and is now unbanned.
        """
        with self._lock:
            removed = self._banned_paths.pop(target_path, None) is not None
            if removed:
                logger.info("path_unbanned", extra={"target_path": target_path})
            return removed

    def is_banned(self, target_path: str) -> bool:
        """Check if a path is currently banned (and clean up expired bans)."""
        now = time.time()
        with self._lock:
            expiry = self._banned_paths.get(target_path)
            if expiry is None:
                return False
            if now >= expiry:
                del self._banned_paths[target_path]
                return False
            return True

    def get_banned_paths(self) -> list[dict]:
        """Return a list of currently banned paths with TTL info."""
        now = time.time()
        with self._lock:
            result = []
            expired = []
            for path, expiry in self._banned_paths.items():
                remaining = expiry - now
                if remaining <= 0:
                    expired.append(path)
                else:
                    result.append({
                        "target_path": path,
                        "remaining_seconds": round(remaining, 1),
                    })
            for p in expired:
                del self._banned_paths[p]
            return result

    def cleanup_expired_bans(self) -> int:
        """Remove all expired bans.  Returns the number removed."""
        now = time.time()
        with self._lock:
            expired = [p for p, exp in self._banned_paths.items() if now >= exp]
            for p in expired:
                del self._banned_paths[p]
            return len(expired)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self, target_path: str, ws, client_ip: str
    ) -> tuple[TunnelConnection | None, str | None]:
        """
        Register a new tunnel connection.

        Args:
            target_path: The URL path prefix this tunnel handles.
            ws:          The WebSocket connection handle.
            client_ip:   The remote IP address of the tunnel client.

        Returns:
            ``(TunnelConnection, None)`` on success.
            ``(None, reason)`` on failure — *reason* is ``"path_in_use"``
            or ``"path_banned"``.
        """
        now = time.time()
        with self._lock:
            # Check ban (clean up if expired)
            expiry = self._banned_paths.get(target_path)
            if expiry is not None:
                if now < expiry:
                    return None, "path_banned"
                else:
                    del self._banned_paths[target_path]

            if target_path in self._tunnels:
                return None, "path_in_use"

            tunnel = TunnelConnection(ws, client_ip)
            self._tunnels[target_path] = tunnel
            self._rebuild_sorted_paths()
            return tunnel, None

    def unregister(self, target_path: str, ws=None) -> None:
        """
        Remove a tunnel registration.

        If *ws* is provided, the tunnel is only removed when the stored
        WebSocket handle matches.  This prevents a race where a new tunnel
        re-registers the same path before the old one's ``finally`` block
        runs.

        Args:
            target_path: The tunnel path to remove.
            ws:          Optional WebSocket handle for ownership verification.
        """
        with self._lock:
            tunnel = self._tunnels.get(target_path)
            if tunnel and (ws is None or tunnel.ws is ws):
                del self._tunnels[target_path]
                ACTIVE_TUNNELS.dec()
                self._rebuild_sorted_paths()
                logger.info(
                    "tunnel_disconnected",
                    extra={"target_path": target_path},
                )

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, target_path: str) -> TunnelConnection | None:
        """Retrieve a tunnel by exact path, or ``None``."""
        with self._lock:
            return self._tunnels.get(target_path)

    def find_longest_match(
        self, full_path: str
    ) -> tuple[str | None, TunnelConnection | None]:
        """
        Find the tunnel whose registered path is the longest prefix of
        *full_path*.

        Uses the pre-sorted path list so no per-request sorting is needed.

        Args:
            full_path: The full incoming request path.

        Returns:
            ``(target_path, TunnelConnection)`` on match, or
            ``(None, None)`` when no tunnel covers *full_path*.
        """
        with self._lock:
            for t_path in self._sorted_paths:
                if full_path.startswith(t_path):
                    tunnel = self._tunnels[t_path]
                    tunnel.increment_requests()
                    return t_path, tunnel
        return None, None

    # ------------------------------------------------------------------
    # Heartbeat Helpers
    # ------------------------------------------------------------------

    def touch(self, target_path: str) -> None:
        """Update the *last_active* timestamp for *target_path*."""
        with self._lock:
            tunnel = self._tunnels.get(target_path)
            if tunnel:
                tunnel.touch()

    def snapshot(self) -> list[tuple[str, TunnelConnection]]:
        """
        Return a point-in-time list of ``(path, tunnel)`` tuples.

        The returned list is a shallow copy so callers can iterate without
        holding the lock (safe for heartbeat pings over the network).
        """
        with self._lock:
            return list(self._tunnels.items())

    def remove_many(self, paths: list[str]) -> None:
        """
        Remove multiple tunnels by path.  Used by the heartbeat reaper.
        Logs a single batched summary instead of one line per path.

        Args:
            paths: Tunnel paths to remove.
        """
        with self._lock:
            removed = []
            for path in paths:
                if path in self._tunnels:
                    del self._tunnels[path]
                    ACTIVE_TUNNELS.dec()
                    removed.append(path)
            if removed:
                self._rebuild_sorted_paths()
                logger.info(
                    "tunnels_reaped",
                    extra={"count": len(removed), "paths": removed},
                )

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def count(self) -> int:
        """Return the number of currently active tunnels."""
        with self._lock:
            return len(self._tunnels)

    def get_tunnels_info(self) -> list[dict]:
        """
        Build serializable tunnel info for admin endpoints.

        Returns:
            List of dicts, each containing tunnel metadata and stats.
        """
        with self._lock:
            result = []
            for path, tunnel in self._tunnels.items():
                info = {"target_path": path}
                info.update(tunnel.to_info_dict())
                result.append(info)
            return result
