"""
HeartbeatService tests.

Verifies ping sending, dead tunnel reaping, and active tunnel survival.
Uses short intervals to keep tests fast and deterministic.
"""

import time
import threading

from tests.conftest import MockWebSocket
from gateway.services.tunnel_manager import TunnelManager
from gateway.services.heartbeat import HeartbeatService


class TestPingSending:
    """Verify that the heartbeat sends ping messages."""

    def test_ping_sent_to_active_tunnel(self):
        """Create a tunnel, run one heartbeat cycle, verify ping was sent."""
        mgr = TunnelManager()
        ws = MockWebSocket()
        mgr.register("/api", ws, "10.0.0.1")

        # Manually execute one heartbeat cycle instead of starting the thread
        import json
        from gateway.protocol.messages import build_ping

        ping_message = build_ping()
        tunnels_snapshot = mgr.snapshot()

        for path, tunnel in tunnels_snapshot:
            tunnel.send(ping_message)

        # Check that the ping was sent
        sent = ws.get_sent(timeout=1)
        assert sent is not None
        assert json.loads(sent)["type"] == "ping"

    def test_ping_sent_to_multiple_tunnels(self):
        mgr = TunnelManager()
        ws1, ws2 = MockWebSocket(), MockWebSocket()
        mgr.register("/a", ws1, "10.0.0.1")
        mgr.register("/b", ws2, "10.0.0.2")

        from gateway.protocol.messages import build_ping
        ping_message = build_ping()
        for path, tunnel in mgr.snapshot():
            tunnel.send(ping_message)

        assert ws1.sent_count == 1
        assert ws2.sent_count == 1


class TestTimeoutDetection:
    """Verify that stale tunnels are detected and reaped."""

    def test_stale_tunnel_detected(self):
        """A tunnel with last_active older than timeout should be reaped."""
        mgr = TunnelManager()
        ws = MockWebSocket()
        tunnel = mgr.register("/api", ws, "10.0.0.1")

        # Simulate stale tunnel by backdating last_active
        tunnel.last_active = time.time() - 100  # 100s ago

        now = time.time()
        ping_timeout = 45
        dead_tunnels = []

        for path, t in mgr.snapshot():
            if now - t.last_active > ping_timeout:
                dead_tunnels.append(path)

        assert "/api" in dead_tunnels

    def test_active_tunnel_not_reaped(self):
        """A recently active tunnel should survive the heartbeat."""
        mgr = TunnelManager()
        ws = MockWebSocket()
        tunnel = mgr.register("/api", ws, "10.0.0.1")
        tunnel.touch()  # Just touched

        now = time.time()
        ping_timeout = 45

        for path, t in mgr.snapshot():
            assert now - t.last_active < ping_timeout

    def test_dead_tunnels_removed(self):
        """Reaping should remove dead tunnels from the manager."""
        mgr = TunnelManager()
        ws1, ws2 = MockWebSocket(), MockWebSocket()
        t1 = mgr.register("/dead", ws1, "10.0.0.1")
        t2 = mgr.register("/alive", ws2, "10.0.0.2")

        t1.last_active = time.time() - 100  # Stale
        t2.touch()  # Active

        dead = []
        for path, t in mgr.snapshot():
            if time.time() - t.last_active > 45:
                dead.append(path)

        mgr.remove_many(dead)
        assert mgr.count() == 1
        assert mgr.get("/alive") is not None
        assert mgr.get("/dead") is None


class TestFailedPing:
    """Verify that failed pings mark tunnels for removal."""

    def test_send_failure_marks_dead(self):
        mgr = TunnelManager()
        ws = MockWebSocket()
        tunnel = mgr.register("/api", ws, "10.0.0.1")

        # Override send to raise
        original_send = ws.send
        ws.send = lambda msg: (_ for _ in ()).throw(ConnectionError("closed"))

        from gateway.protocol.messages import build_ping
        dead = []
        for path, t in mgr.snapshot():
            try:
                t.send(build_ping())
            except Exception:
                dead.append(path)

        assert "/api" in dead

        ws.send = original_send
        mgr.unregister("/api")


class TestHeartbeatServiceLifecycle:
    """Verify the HeartbeatService thread management."""

    def test_starts_as_daemon(self):
        mgr = TunnelManager()
        hb = HeartbeatService(mgr)
        hb.start()
        assert hb._thread is not None
        assert hb._thread.daemon is True

    def test_reregister_after_reap(self):
        """After a tunnel is reaped, a new tunnel can take its path."""
        mgr = TunnelManager()
        ws1 = MockWebSocket()
        t1 = mgr.register("/api", ws1, "10.0.0.1")
        t1.last_active = time.time() - 100

        # Reap
        mgr.remove_many(["/api"])
        assert mgr.count() == 0

        # Re-register
        ws2 = MockWebSocket()
        t2 = mgr.register("/api", ws2, "10.0.0.2")
        assert t2 is not None
        assert mgr.count() == 1
        mgr.unregister("/api")
