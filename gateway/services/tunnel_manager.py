"""
TunnelManager service.

Thread-safe registry for active WebSocket tunnel connections.
Handles registration, deregistration, longest-prefix matching,
and provides snapshots for admin reporting and heartbeat iteration.
"""

import threading

from gateway.models.tunnel import TunnelConnection
from gateway.utils.log import get_logger

logger = get_logger()


class TunnelManager:
    """
    Manages the lifecycle of active tunnel connections.

    All public methods are thread-safe through an internal lock.  Methods
    that iterate over tunnels (``snapshot``, ``get_tunnels_info``) return
    copies so callers never hold the lock during slow operations such as
    network I/O.
    """

    def __init__(self):
        self._tunnels: dict[str, TunnelConnection] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, target_path: str, ws, client_ip: str) -> TunnelConnection | None:
        """
        Register a new tunnel connection.

        Args:
            target_path: The URL path prefix this tunnel handles.
            ws:          The WebSocket connection handle.
            client_ip:   The remote IP address of the tunnel client.

        Returns:
            A new :class:`TunnelConnection` on success, or ``None`` if
            *target_path* is already occupied by another tunnel.
        """
        with self._lock:
            if target_path in self._tunnels:
                return None
            tunnel = TunnelConnection(ws, client_ip)
            self._tunnels[target_path] = tunnel
            return tunnel

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
                logger.info(f"Tunnel disconnected and cleaned up: {target_path}")

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, target_path: str) -> TunnelConnection | None:
        """Retrieve a tunnel by exact path, or ``None``."""
        with self._lock:
            return self._tunnels.get(target_path)

    def find_longest_match(self, full_path: str) -> tuple[str | None, TunnelConnection | None]:
        """
        Find the tunnel whose registered path is the longest prefix of
        *full_path*.

        On a successful match the tunnel's served-request counter is
        incremented atomically (under the lock).

        Args:
            full_path: The full incoming request path.

        Returns:
            ``(target_path, TunnelConnection)`` on match, or
            ``(None, None)`` when no tunnel covers *full_path*.
        """
        with self._lock:
            for t_path in sorted(self._tunnels.keys(), key=len, reverse=True):
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

        Args:
            paths: Tunnel paths to remove.
        """
        with self._lock:
            for path in paths:
                if path in self._tunnels:
                    logger.info(f"Reaping dead tunnel: {path}")
                    del self._tunnels[path]

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

        The ``target_path`` key is prepended so the dict ordering matches
        the original API contract.

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
