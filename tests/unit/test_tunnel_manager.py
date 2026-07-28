"""
Unit tests for gateway.services.tunnel_manager.TunnelManager.

Verifies registration, deregistration, longest-prefix matching,
snapshots, batch removal, counting, and admin info serialization.
"""

import threading

from tests.conftest import MockWebSocket
from gateway.services.tunnel_manager import TunnelManager


class TestRegister:
    """Tests for tunnel registration."""

    def test_register_success(self):
        mgr = TunnelManager()
        ws = MockWebSocket()
        tunnel = mgr.register("/api", ws, "10.0.0.1")
        assert tunnel is not None
        assert tunnel.client_ip == "10.0.0.1"
        assert tunnel.ws is ws

    def test_register_duplicate_returns_none(self):
        mgr = TunnelManager()
        mgr.register("/api", MockWebSocket(), "10.0.0.1")
        result = mgr.register("/api", MockWebSocket(), "10.0.0.2")
        assert result is None

    def test_register_different_paths(self):
        mgr = TunnelManager()
        t1 = mgr.register("/api", MockWebSocket(), "10.0.0.1")
        t2 = mgr.register("/web", MockWebSocket(), "10.0.0.2")
        assert t1 is not None
        assert t2 is not None
        assert mgr.count() == 2

    def test_register_nested_paths(self):
        mgr = TunnelManager()
        t1 = mgr.register("/api", MockWebSocket(), "10.0.0.1")
        t2 = mgr.register("/api/v2", MockWebSocket(), "10.0.0.2")
        assert t1 is not None
        assert t2 is not None


class TestUnregister:
    """Tests for tunnel deregistration."""

    def test_unregister_removes_tunnel(self):
        mgr = TunnelManager()
        mgr.register("/api", MockWebSocket(), "10.0.0.1")
        mgr.unregister("/api")
        assert mgr.count() == 0

    def test_unregister_nonexistent_is_safe(self):
        mgr = TunnelManager()
        mgr.unregister("/nonexistent")  # Should not raise

    def test_unregister_with_ws_check_passes(self):
        mgr = TunnelManager()
        ws = MockWebSocket()
        mgr.register("/api", ws, "10.0.0.1")
        mgr.unregister("/api", ws=ws)
        assert mgr.count() == 0

    def test_unregister_wrong_ws_keeps_tunnel(self):
        """Unregister should not remove if ws doesn't match."""
        mgr = TunnelManager()
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        mgr.register("/api", ws1, "10.0.0.1")
        mgr.unregister("/api", ws=ws2)
        assert mgr.count() == 1  # Still registered

    def test_reregister_after_unregister(self):
        mgr = TunnelManager()
        mgr.register("/api", MockWebSocket(), "10.0.0.1")
        mgr.unregister("/api")
        tunnel = mgr.register("/api", MockWebSocket(), "10.0.0.2")
        assert tunnel is not None


class TestGet:
    """Tests for exact-path lookup."""

    def test_get_existing(self):
        mgr = TunnelManager()
        ws = MockWebSocket()
        mgr.register("/api", ws, "10.0.0.1")
        tunnel = mgr.get("/api")
        assert tunnel is not None
        assert tunnel.ws is ws

    def test_get_nonexistent(self):
        mgr = TunnelManager()
        assert mgr.get("/nope") is None


class TestLongestPrefixMatch:
    """Tests for find_longest_match."""

    def test_exact_match(self):
        mgr = TunnelManager()
        mgr.register("/api", MockWebSocket(), "10.0.0.1")
        path, tunnel = mgr.find_longest_match("/api")
        assert path == "/api"
        assert tunnel is not None

    def test_prefix_match(self):
        mgr = TunnelManager()
        mgr.register("/api", MockWebSocket(), "10.0.0.1")
        path, tunnel = mgr.find_longest_match("/api/users")
        assert path == "/api"

    def test_longest_prefix_wins(self):
        mgr = TunnelManager()
        mgr.register("/api", MockWebSocket(), "10.0.0.1")
        mgr.register("/api/v2", MockWebSocket(), "10.0.0.2")
        path, tunnel = mgr.find_longest_match("/api/v2/users")
        assert path == "/api/v2"

    def test_no_match_returns_none(self):
        mgr = TunnelManager()
        mgr.register("/api", MockWebSocket(), "10.0.0.1")
        path, tunnel = mgr.find_longest_match("/other")
        assert path is None
        assert tunnel is None

    def test_match_increments_requests(self):
        mgr = TunnelManager()
        mgr.register("/api", MockWebSocket(), "10.0.0.1")
        _, tunnel = mgr.find_longest_match("/api")
        assert tunnel.requests_served == 1
        mgr.find_longest_match("/api/again")
        assert tunnel.requests_served == 2

    def test_root_matches_everything(self):
        mgr = TunnelManager()
        mgr.register("/", MockWebSocket(), "10.0.0.1")
        path, tunnel = mgr.find_longest_match("/anything")
        assert path == "/"


class TestTouch:
    """Tests for heartbeat timestamp update."""

    def test_touch_updates(self):
        mgr = TunnelManager()
        mgr.register("/api", MockWebSocket(), "10.0.0.1")
        tunnel = mgr.get("/api")
        old = tunnel.last_active

        import time
        time.sleep(0.01)
        mgr.touch("/api")
        assert tunnel.last_active > old

    def test_touch_nonexistent_is_safe(self):
        mgr = TunnelManager()
        mgr.touch("/nope")  # Should not raise


class TestSnapshot:
    """Tests for snapshot."""

    def test_snapshot_empty(self):
        mgr = TunnelManager()
        assert mgr.snapshot() == []

    def test_snapshot_returns_copy(self):
        mgr = TunnelManager()
        mgr.register("/api", MockWebSocket(), "10.0.0.1")
        snap = mgr.snapshot()
        assert len(snap) == 1
        assert snap[0][0] == "/api"

    def test_snapshot_decoupled_from_mutations(self):
        mgr = TunnelManager()
        mgr.register("/api", MockWebSocket(), "10.0.0.1")
        snap = mgr.snapshot()
        mgr.register("/web", MockWebSocket(), "10.0.0.2")
        assert len(snap) == 1  # Original snapshot unchanged


class TestRemoveMany:
    """Tests for batch removal."""

    def test_remove_many(self):
        mgr = TunnelManager()
        mgr.register("/a", MockWebSocket(), "10.0.0.1")
        mgr.register("/b", MockWebSocket(), "10.0.0.2")
        mgr.register("/c", MockWebSocket(), "10.0.0.3")
        mgr.remove_many(["/a", "/c"])
        assert mgr.count() == 1
        assert mgr.get("/b") is not None

    def test_remove_many_nonexistent_is_safe(self):
        mgr = TunnelManager()
        mgr.remove_many(["/nope1", "/nope2"])


class TestGetTunnelsInfo:
    """Tests for admin info serialization."""

    def test_empty(self):
        mgr = TunnelManager()
        assert mgr.get_tunnels_info() == []

    def test_includes_target_path(self):
        mgr = TunnelManager()
        mgr.register("/api", MockWebSocket(), "10.0.0.1")
        info = mgr.get_tunnels_info()
        assert len(info) == 1
        assert info[0]["target_path"] == "/api"

    def test_target_path_is_first_key(self):
        """Preserve JSON field order for API compatibility."""
        mgr = TunnelManager()
        mgr.register("/api", MockWebSocket(), "10.0.0.1")
        info = mgr.get_tunnels_info()[0]
        assert list(info.keys())[0] == "target_path"


class TestThreadSafety:
    """Stress test for concurrent operations."""

    def test_concurrent_register_unregister(self):
        mgr = TunnelManager()
        barrier = threading.Barrier(20)

        def worker(i):
            barrier.wait()
            path = f"/tunnel-{i}"
            ws = MockWebSocket()
            mgr.register(path, ws, "10.0.0.1")
            mgr.touch(path)
            mgr.find_longest_match(path)
            mgr.unregister(path)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert mgr.count() == 0
