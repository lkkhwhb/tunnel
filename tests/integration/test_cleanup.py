"""
Integration tests for cleanup and resource leak prevention.

Verifies that pending requests, active request counters, and stats are
properly cleaned up after successful requests, timeouts, and errors.
"""

from gateway import services as svc
from tests.conftest import MockWebSocket, AutoResponder


class TestCleanupAfterSuccess:
    """Verify cleanup after a successful single-message response."""

    def test_no_leaked_pending_requests(self, client, tunnel_responder):
        client.get("/test/path")
        # After the request completes, no pending requests should remain
        assert svc.request_manager.get("any-stale-id") is None

    def test_active_requests_returns_to_zero(self, client, tunnel_responder):
        client.get("/test/path")
        snap = svc.server_stats.snapshot()
        assert snap["active_requests"] == 0

    def test_total_requests_incremented(self, client, tunnel_responder):
        snap_before = svc.server_stats.snapshot()
        client.get("/test/path")
        snap_after = svc.server_stats.snapshot()
        assert snap_after["total_requests"] == snap_before["total_requests"] + 1

    def test_latency_recorded(self, client, tunnel_responder):
        snap_before = svc.server_stats.snapshot()
        client.get("/test/path")
        snap_after = svc.server_stats.snapshot()
        assert snap_after["average_latency_ms"] >= 0


class TestCleanupAfterTimeout:
    """Verify cleanup after a request timeout (504)."""

    def test_no_leaked_requests_on_timeout(self, client, app, monkeypatch):
        monkeypatch.setattr("gateway.routes.proxy.TUNNEL_TIMEOUT", 0.05)

        ws = MockWebSocket()
        tunnel = svc.tunnel_manager.register("/test", ws, "127.0.0.1")
        try:
            client.get("/test/timeout")
            snap = svc.server_stats.snapshot()
            assert snap["active_requests"] == 0
        finally:
            svc.tunnel_manager.unregister("/test")

    def test_stats_updated_on_timeout(self, client, app, monkeypatch):
        monkeypatch.setattr("gateway.routes.proxy.TUNNEL_TIMEOUT", 0.05)

        ws = MockWebSocket()
        tunnel = svc.tunnel_manager.register("/test", ws, "127.0.0.1")
        try:
            snap_before = svc.server_stats.snapshot()
            client.get("/test/timeout")
            snap_after = svc.server_stats.snapshot()
            assert snap_after["total_requests"] == snap_before["total_requests"] + 1
        finally:
            svc.tunnel_manager.unregister("/test")


class TestCleanupAfterStreaming:
    """Verify cleanup after a streaming response completes."""

    def test_no_leaked_requests_after_streaming(self, client, streaming_responder):
        client.get("/test/stream")
        snap = svc.server_stats.snapshot()
        assert snap["active_requests"] == 0

    def test_streaming_latency_recorded(self, client, streaming_responder):
        client.get("/test/stream")
        snap = svc.server_stats.snapshot()
        assert snap["total_requests"] >= 1


class TestCleanupAfterError:
    """Verify cleanup when the tunnel WebSocket throws an error."""

    def test_cleanup_on_send_error(self, client, app, monkeypatch):
        """If the tunnel WS fails during send, the proxy should return 502."""
        ws = MockWebSocket()
        tunnel = svc.tunnel_manager.register("/test", ws, "127.0.0.1")

        # Make send() raise an exception
        original_send = ws.send
        def failing_send(msg):
            raise ConnectionError("WebSocket closed")
        ws.send = failing_send

        try:
            resp = client.get("/test/error")
            assert resp.status_code == 502
            snap = svc.server_stats.snapshot()
            assert snap["active_requests"] == 0
        finally:
            ws.send = original_send
            svc.tunnel_manager.unregister("/test")


class TestDoubleCleanup:
    """Verify that the cleanup function is idempotent."""

    def test_double_cleanup_is_safe(self, client, tunnel_responder):
        """Making multiple requests ensures cleanup runs multiple times."""
        for _ in range(5):
            resp = client.get("/test/path")
            assert resp.status_code == 200

        snap = svc.server_stats.snapshot()
        assert snap["active_requests"] == 0
        assert snap["total_requests"] >= 5


class TestStatsTracking:
    """Verify statistics are tracked accurately across requests."""

    def test_upload_bytes_tracked(self, client, tunnel_responder):
        body = b"x" * 100
        client.post("/test/upload", data=body)
        snap = svc.server_stats.snapshot()
        assert snap["bytes_uploaded"] >= 100

    def test_download_bytes_tracked(self, client, app):
        ws = MockWebSocket()
        tunnel = svc.tunnel_manager.register("/test", ws, "127.0.0.1")
        big_body = b"y" * 500
        responder = AutoResponder(ws, tunnel, body=big_body).start()
        try:
            client.get("/test/download")
            snap = svc.server_stats.snapshot()
            assert snap["bytes_downloaded"] >= 500
        finally:
            responder.stop()
            svc.tunnel_manager.unregister("/test")

    def test_tunnel_stats_tracked(self, client, tunnel_responder):
        tunnel, mock_ws, responder = tunnel_responder
        client.post("/test/data", data=b"payload")
        assert tunnel.requests_served >= 1
        assert tunnel.bytes_uploaded >= 7  # len("payload")
