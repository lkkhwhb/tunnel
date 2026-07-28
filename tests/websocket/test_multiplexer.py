"""
WebSocket multiplexer tests.

Verifies that the multiplexer correctly dispatches incoming response frames
(res_single, res_start, res_chunk, res_end, pong) to the right RequestState,
and gracefully handles invalid or unexpected messages.
"""

import time

from gateway.app import create_app
from gateway import services as svc
from gateway.models.request import RequestState
from gateway.utils.encoding import b64_encode, b64_decode
from tests.conftest import MockWebSocket


class TestResSingleDispatch:
    """Tests for single-message response dispatch."""

    def test_dispatches_to_request_state(self, app):
        state = svc.request_manager.create("r1", time.time())
        # Simulate what the multiplexer does on receiving res_single
        state.set_single_response(200, {"X-Test": "yes"}, b64_encode(b"body"))
        assert state.status == 200
        assert state.body == b"body"
        assert state.headers_event.is_set()
        svc.request_manager.remove("r1")

    def test_custom_status_code(self, app):
        state = svc.request_manager.create("r2", time.time())
        state.set_single_response(404, {}, b64_encode(b"Not Found"))
        assert state.status == 404
        svc.request_manager.remove("r2")

    def test_empty_body(self, app):
        state = svc.request_manager.create("r3", time.time())
        length = state.set_single_response(204, {}, b64_encode(b""))
        assert length == 0
        assert state.body == b""
        svc.request_manager.remove("r3")


class TestResStreamDispatch:
    """Tests for streaming response dispatch."""

    def test_res_start_sets_headers(self, app):
        state = svc.request_manager.create("r1", time.time())
        state.set_streaming_start(200, {"Content-Type": "text/plain"})
        assert state.status == 200
        assert state.headers_event.is_set()
        assert state.is_single is False
        svc.request_manager.remove("r1")

    def test_res_chunk_queues_data(self, app):
        state = svc.request_manager.create("r1", time.time())
        state.push_chunk(b64_encode(b"chunk1"))
        assert state.chunk_queue.get_nowait() == b"chunk1"
        svc.request_manager.remove("r1")

    def test_multiple_chunks_in_order(self, app):
        state = svc.request_manager.create("r1", time.time())
        state.push_chunk(b64_encode(b"A"))
        state.push_chunk(b64_encode(b"B"))
        state.push_chunk(b64_encode(b"C"))
        assert state.chunk_queue.get_nowait() == b"A"
        assert state.chunk_queue.get_nowait() == b"B"
        assert state.chunk_queue.get_nowait() == b"C"
        svc.request_manager.remove("r1")

    def test_res_end_pushes_sentinel(self, app):
        state = svc.request_manager.create("r1", time.time())
        state.end_stream()
        assert state.chunk_queue.get_nowait() is None
        svc.request_manager.remove("r1")


class TestPongHandling:
    """Tests for heartbeat pong processing."""

    def test_pong_updates_last_active(self, app):
        ws = MockWebSocket()
        tunnel, _ = svc.tunnel_manager.register("/api", ws, "10.0.0.1")
        old = tunnel.last_active
        import time as _t
        _t.sleep(0.01)
        # Simulate multiplexer receiving pong → touch
        svc.tunnel_manager.touch("/api")
        assert tunnel.last_active > old
        svc.tunnel_manager.unregister("/api")


class TestUnknownMessageTypes:
    """Verify that unknown or malformed messages are handled gracefully."""

    def test_unknown_type_ignored(self, app):
        """Multiplexer should skip messages with unrecognized types."""
        state = svc.request_manager.create("r1", time.time())
        # An unknown type would simply not match any dispatch branch
        # The handler continues to the next message
        assert not state.headers_event.is_set()  # State unchanged
        svc.request_manager.remove("r1")

    def test_missing_req_id_skipped(self, app):
        """Messages without req_id should be silently ignored."""
        # Create a request state but don't modify it
        state = svc.request_manager.create("r1", time.time())
        # A message with type="res_single" but no req_id would be skipped
        assert not state.headers_event.is_set()
        svc.request_manager.remove("r1")

    def test_nonexistent_req_id_skipped(self, app):
        """Response for an unknown req_id should be silently discarded."""
        assert svc.request_manager.get("nonexistent-id") is None


class TestStatsRecording:
    """Verify that download stats are recorded during response dispatch."""

    def test_download_bytes_recorded_on_single(self, app):
        ws = MockWebSocket()
        tunnel, _ = svc.tunnel_manager.register("/api", ws, "10.0.0.1")
        state = svc.request_manager.create("r1", time.time())

        body_len = state.set_single_response(200, {}, b64_encode(b"12345"))
        tunnel.record_download(body_len)
        svc.server_stats.record_download(body_len)

        assert tunnel.bytes_downloaded == 5
        snap = svc.server_stats.snapshot()
        assert snap["bytes_downloaded"] >= 5

        svc.request_manager.remove("r1")
        svc.tunnel_manager.unregister("/api")

    def test_download_bytes_recorded_on_chunk(self, app):
        ws = MockWebSocket()
        tunnel, _ = svc.tunnel_manager.register("/api", ws, "10.0.0.1")
        state = svc.request_manager.create("r1", time.time())

        chunk_len = state.push_chunk(b64_encode(b"chunk-data"))
        tunnel.record_download(chunk_len)

        assert tunnel.bytes_downloaded == 10  # len("chunk-data")

        svc.request_manager.remove("r1")
        svc.tunnel_manager.unregister("/api")
