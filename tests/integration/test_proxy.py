"""
Integration tests for the catch-all proxy route.

Tests every HTTP method, header forwarding, body handling, path matching,
timeout behavior, error cases, and both single-message and streaming modes.
"""

import json

from gateway import services as svc
from gateway.utils.encoding import b64_decode
from tests.conftest import MockWebSocket, AutoResponder


class TestNoTunnel:
    """Tests when no tunnel is registered."""

    def test_no_tunnel_returns_404(self, client, app):
        resp = client.get("/anything")
        assert resp.status_code == 404

    def test_404_message(self, client, app):
        resp = client.get("/anything")
        assert b"No active tunnel" in resp.data


class TestAdminWakeGuard:
    """Verify that admin and wake paths are never proxied."""

    def test_admin_path_returns_404(self, client, tunnel_responder):
        resp = client.get("/admin/status-fake")
        assert resp.status_code == 404

    def test_wake_path_returns_404_when_proxied(self, client, app):
        """The wake path is handled by its own blueprint, not the proxy."""
        # Even with a tunnel at /, wake should be handled by the wake bp
        ws = MockWebSocket()
        tunnel = svc.tunnel_manager.register("/", ws, "127.0.0.1")
        responder = AutoResponder(ws, tunnel).start()
        try:
            resp = client.get("/wake")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "awake"  # Served by wake bp, not proxy
        finally:
            responder.stop()
            svc.tunnel_manager.unregister("/")


class TestHTTPMethods:
    """Verify all HTTP methods are proxied correctly."""

    def test_get(self, client, tunnel_responder):
        resp = client.get("/test/path")
        assert resp.status_code == 200
        assert resp.data == b"OK"

    def test_post(self, client, tunnel_responder):
        resp = client.post("/test/path", data=b"body")
        assert resp.status_code == 200

    def test_put(self, client, tunnel_responder):
        resp = client.put("/test/path", data=b"body")
        assert resp.status_code == 200

    def test_patch(self, client, tunnel_responder):
        resp = client.patch("/test/path", data=b"patch")
        assert resp.status_code == 200

    def test_delete(self, client, tunnel_responder):
        resp = client.delete("/test/path")
        assert resp.status_code == 200

    def test_head(self, client, tunnel_responder):
        resp = client.head("/test/path")
        assert resp.status_code == 200

    def test_options(self, client, tunnel_responder):
        resp = client.options("/test/path")
        assert resp.status_code == 200


class TestHeaderForwarding:
    """Verify request headers are forwarded to the tunnel."""

    def test_custom_header_forwarded(self, client, tunnel_responder):
        tunnel, mock_ws, responder = tunnel_responder
        client.get("/test/path", headers={"X-Custom": "value"})

        # Check the captured request
        assert len(responder.captured_requests) == 1
        req = responder.captured_requests[0]
        assert req["headers"]["X-Custom"] == "value"

    def test_host_header_removed(self, client, tunnel_responder):
        tunnel, mock_ws, responder = tunnel_responder
        client.get("/test/path")

        req = responder.captured_requests[0]
        assert "Host" not in req["headers"]

    def test_content_type_forwarded(self, client, tunnel_responder):
        tunnel, mock_ws, responder = tunnel_responder
        client.post(
            "/test/path",
            data=json.dumps({"key": "value"}),
            content_type="application/json",
        )
        req = responder.captured_requests[0]
        assert "application/json" in req["headers"].get("Content-Type", "")


class TestQueryString:
    """Verify query string forwarding."""

    def test_query_forwarded(self, client, tunnel_responder):
        tunnel, mock_ws, responder = tunnel_responder
        client.get("/test/path?page=1&limit=10")

        req = responder.captured_requests[0]
        assert req["query"] == "page=1&limit=10"

    def test_empty_query(self, client, tunnel_responder):
        tunnel, mock_ws, responder = tunnel_responder
        client.get("/test/path")

        req = responder.captured_requests[0]
        assert req["query"] == ""


class TestSubpathComputation:
    """Verify subpath is computed correctly after prefix stripping."""

    def test_subpath_with_prefix(self, client, tunnel_responder):
        tunnel, mock_ws, responder = tunnel_responder
        client.get("/test/users/42")

        req = responder.captured_requests[0]
        assert req["subpath"] == "/users/42"

    def test_subpath_at_root(self, client, tunnel_responder):
        tunnel, mock_ws, responder = tunnel_responder
        client.get("/test")

        req = responder.captured_requests[0]
        assert req["subpath"] == "/"


class TestBodyForwarding:
    """Verify request body is forwarded correctly."""

    def test_json_body(self, client, tunnel_responder):
        tunnel, mock_ws, responder = tunnel_responder
        payload = json.dumps({"name": "test"})
        client.post("/test/api", data=payload, content_type="application/json")

        req = responder.captured_requests[0]
        decoded_body = b64_decode(req["body"])
        assert json.loads(decoded_body) == {"name": "test"}

    def test_binary_body(self, client, tunnel_responder):
        tunnel, mock_ws, responder = tunnel_responder
        binary = bytes(range(256))
        client.post("/test/upload", data=binary)

        req = responder.captured_requests[0]
        assert b64_decode(req["body"]) == binary

    def test_empty_body(self, client, tunnel_responder):
        tunnel, mock_ws, responder = tunnel_responder
        client.get("/test/path")

        req = responder.captured_requests[0]
        assert b64_decode(req["body"]) == b""


class TestResponseHandling:
    """Verify proxy returns tunnel responses correctly."""

    def test_custom_status_code(self, client, app):
        ws = MockWebSocket()
        tunnel = svc.tunnel_manager.register("/test", ws, "127.0.0.1")
        responder = AutoResponder(ws, tunnel, status=201, body=b"Created").start()
        try:
            resp = client.post("/test/resource", data=b"new")
            assert resp.status_code == 201
            assert resp.data == b"Created"
        finally:
            responder.stop()
            svc.tunnel_manager.unregister("/test")

    def test_custom_response_headers(self, client, app):
        ws = MockWebSocket()
        tunnel = svc.tunnel_manager.register("/test", ws, "127.0.0.1")
        responder = AutoResponder(
            ws, tunnel,
            headers={"X-Custom-Response": "yes", "Content-Type": "application/json"},
        ).start()
        try:
            resp = client.get("/test/path")
            assert resp.headers.get("X-Custom-Response") == "yes"
        finally:
            responder.stop()
            svc.tunnel_manager.unregister("/test")

    def test_404_response(self, client, app):
        ws = MockWebSocket()
        tunnel = svc.tunnel_manager.register("/test", ws, "127.0.0.1")
        responder = AutoResponder(ws, tunnel, status=404, body=b"Not Found").start()
        try:
            resp = client.get("/test/missing")
            assert resp.status_code == 404
            assert resp.data == b"Not Found"
        finally:
            responder.stop()
            svc.tunnel_manager.unregister("/test")

    def test_500_response(self, client, app):
        ws = MockWebSocket()
        tunnel = svc.tunnel_manager.register("/test", ws, "127.0.0.1")
        responder = AutoResponder(ws, tunnel, status=500, body=b"Error").start()
        try:
            resp = client.get("/test/fail")
            assert resp.status_code == 500
        finally:
            responder.stop()
            svc.tunnel_manager.unregister("/test")


class TestStreamingResponse:
    """Verify streaming response mode."""

    def test_streaming_response_concatenated(self, client, streaming_responder):
        resp = client.get("/test/stream")
        assert resp.status_code == 200
        assert resp.data == b"chunk1chunk2chunk3"

    def test_streaming_content_type(self, client, streaming_responder):
        resp = client.get("/test/stream")
        assert "application/octet-stream" in resp.content_type


class TestTimeout:
    """Verify timeout behavior when tunnel doesn't respond."""

    def test_timeout_returns_504(self, client, app, monkeypatch):
        # Use a very short timeout for testing
        monkeypatch.setattr("gateway.routes.proxy.TUNNEL_TIMEOUT", 0.1)

        ws = MockWebSocket()
        tunnel = svc.tunnel_manager.register("/test", ws, "127.0.0.1")
        # No responder → timeout
        try:
            resp = client.get("/test/timeout")
            assert resp.status_code == 504
            assert b"Gateway Timeout" in resp.data
        finally:
            svc.tunnel_manager.unregister("/test")


class TestLongestPrefixMatch:
    """Verify longest-prefix path matching in proxy routing."""

    def test_longer_prefix_wins(self, client, app):
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        t1 = svc.tunnel_manager.register("/api", ws1, "127.0.0.1")
        t2 = svc.tunnel_manager.register("/api/v2", ws2, "127.0.0.2")
        r1 = AutoResponder(ws1, t1, body=b"v1").start()
        r2 = AutoResponder(ws2, t2, body=b"v2").start()

        try:
            resp = client.get("/api/v2/users")
            assert resp.data == b"v2"

            resp = client.get("/api/users")
            assert resp.data == b"v1"
        finally:
            r1.stop()
            r2.stop()
            svc.tunnel_manager.unregister("/api")
            svc.tunnel_manager.unregister("/api/v2")
