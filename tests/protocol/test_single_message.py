"""
Protocol-level tests for single-message mode.

Verifies end-to-end single-message request/response for various payload
types: small text, binary, unicode, empty body, and JSON content.
"""

import json

from gateway import services as svc
from gateway.utils.encoding import b64_encode, b64_decode
from tests.conftest import MockWebSocket, AutoResponder


class TestSmallTextPayload:
    """Tests for simple text payloads."""

    def test_text_roundtrip(self, client, tunnel_responder):
        tunnel, mock_ws, responder = tunnel_responder
        resp = client.post("/test/echo", data=b"hello world")
        assert resp.status_code == 200

        req = responder.captured_requests[0]
        assert b64_decode(req["body"]) == b"hello world"

    def test_response_body_correct(self, client, tunnel_responder):
        resp = client.get("/test/path")
        assert resp.data == b"OK"


class TestBinaryPayload:
    """Tests for binary payloads with all byte values."""

    def test_all_bytes_roundtrip(self, client, tunnel_responder):
        tunnel, mock_ws, responder = tunnel_responder
        binary = bytes(range(256))
        client.post("/test/binary", data=binary)

        req = responder.captured_requests[0]
        assert b64_decode(req["body"]) == binary

    def test_null_bytes(self, client, tunnel_responder):
        tunnel, mock_ws, responder = tunnel_responder
        data = b"\x00\x00\x00"
        client.post("/test/null", data=data)

        req = responder.captured_requests[0]
        assert b64_decode(req["body"]) == data

    def test_binary_response(self, client, app):
        ws = MockWebSocket()
        tunnel, _ = svc.tunnel_manager.register("/test", ws, "127.0.0.1")
        binary_body = bytes(range(256))
        responder = AutoResponder(ws, tunnel, body=binary_body).start()
        try:
            resp = client.get("/test/binary")
            assert resp.data == binary_body
        finally:
            responder.stop()
            svc.tunnel_manager.unregister("/test")


class TestUnicodePayload:
    """Tests for unicode text payloads."""

    def test_unicode_body(self, client, tunnel_responder):
        tunnel, mock_ws, responder = tunnel_responder
        text = "こんにちは世界 🌍 café résumé"
        client.post("/test/unicode", data=text.encode("utf-8"))

        req = responder.captured_requests[0]
        assert b64_decode(req["body"]) == text.encode("utf-8")

    def test_unicode_response(self, client, app):
        ws = MockWebSocket()
        tunnel, _ = svc.tunnel_manager.register("/test", ws, "127.0.0.1")
        body = "Ñoño señor".encode("utf-8")
        responder = AutoResponder(ws, tunnel, body=body).start()
        try:
            resp = client.get("/test/unicode")
            assert resp.data == body
        finally:
            responder.stop()
            svc.tunnel_manager.unregister("/test")


class TestEmptyBody:
    """Tests for requests with no body."""

    def test_get_has_empty_body(self, client, tunnel_responder):
        tunnel, mock_ws, responder = tunnel_responder
        client.get("/test/path")

        req = responder.captured_requests[0]
        assert b64_decode(req["body"]) == b""

    def test_empty_post_body(self, client, tunnel_responder):
        tunnel, mock_ws, responder = tunnel_responder
        client.post("/test/path", data=b"")

        req = responder.captured_requests[0]
        assert b64_decode(req["body"]) == b""


class TestJSONPayload:
    """Tests for JSON request/response bodies."""

    def test_json_body_forwarded(self, client, tunnel_responder):
        tunnel, mock_ws, responder = tunnel_responder
        payload = {"key": "value", "number": 42, "nested": {"a": 1}}
        client.post(
            "/test/json",
            data=json.dumps(payload),
            content_type="application/json",
        )

        req = responder.captured_requests[0]
        decoded = json.loads(b64_decode(req["body"]))
        assert decoded == payload

    def test_json_response(self, client, app):
        ws = MockWebSocket()
        tunnel, _ = svc.tunnel_manager.register("/test", ws, "127.0.0.1")
        json_body = json.dumps({"result": "success"}).encode()
        responder = AutoResponder(
            ws, tunnel, body=json_body,
            headers={"Content-Type": "application/json"},
        ).start()
        try:
            resp = client.get("/test/json")
            assert resp.get_json() == {"result": "success"}
        finally:
            responder.stop()
            svc.tunnel_manager.unregister("/test")


class TestMessageFormat:
    """Verify the req_single message structure."""

    def test_req_single_has_all_fields(self, client, tunnel_responder):
        tunnel, mock_ws, responder = tunnel_responder
        client.post(
            "/test/path?q=1",
            data=b"body",
            headers={"X-Test": "yes"},
        )

        req = responder.captured_requests[0]
        assert req["type"] == "req_single"
        assert "req_id" in req
        assert req["method"] == "POST"
        assert req["subpath"] == "/path"
        assert req["query"] == "q=1"
        assert "X-Test" in req["headers"]
        assert isinstance(req["body"], str)  # base64

    def test_req_id_is_uuid_format(self, client, tunnel_responder):
        tunnel, mock_ws, responder = tunnel_responder
        client.get("/test/path")
        req = responder.captured_requests[0]
        parts = req["req_id"].split("-")
        assert len(parts) == 5  # UUID v4 format
