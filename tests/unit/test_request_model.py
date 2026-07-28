"""
Unit tests for gateway.models.request.RequestState.

Verifies single-message response handling, streaming, header filtering,
timeout behavior, and latency computation.
"""

import time
import threading
import queue

from gateway.models.request import RequestState
from gateway.utils.encoding import b64_encode


class TestConstruction:
    """Verify initial defaults."""

    def test_defaults(self):
        state = RequestState("req-1", time.time())
        assert state.req_id == "req-1"
        assert state.status == 500
        assert state.headers == {}
        assert state.is_single is False
        assert state.body == b""

    def test_event_not_set(self):
        state = RequestState("req-1", time.time())
        assert not state.headers_event.is_set()

    def test_queue_empty(self):
        state = RequestState("req-1", time.time())
        assert state.chunk_queue.empty()


class TestSingleResponse:
    """Tests for set_single_response."""

    def test_sets_status_and_headers(self):
        state = RequestState("req-1", time.time())
        state.set_single_response(200, {"X-Custom": "val"}, b64_encode(b"OK"))
        assert state.status == 200
        assert state.headers == {"X-Custom": "val"}

    def test_decodes_body(self):
        state = RequestState("req-1", time.time())
        state.set_single_response(200, {}, b64_encode(b"Hello World"))
        assert state.body == b"Hello World"

    def test_sets_is_single_flag(self):
        state = RequestState("req-1", time.time())
        state.set_single_response(200, {}, b64_encode(b""))
        assert state.is_single is True

    def test_sets_headers_event(self):
        state = RequestState("req-1", time.time())
        state.set_single_response(200, {}, b64_encode(b""))
        assert state.headers_event.is_set()

    def test_returns_body_length(self):
        state = RequestState("req-1", time.time())
        length = state.set_single_response(200, {}, b64_encode(b"12345"))
        assert length == 5

    def test_binary_body(self):
        data = bytes(range(256))
        state = RequestState("req-1", time.time())
        state.set_single_response(200, {}, b64_encode(data))
        assert state.body == data

    def test_empty_body(self):
        state = RequestState("req-1", time.time())
        length = state.set_single_response(204, {}, b64_encode(b""))
        assert length == 0
        assert state.body == b""


class TestStreamingResponse:
    """Tests for streaming response methods."""

    def test_set_streaming_start(self):
        state = RequestState("req-1", time.time())
        state.set_streaming_start(200, {"Content-Type": "text/plain"})
        assert state.status == 200
        assert state.headers == {"Content-Type": "text/plain"}
        assert state.headers_event.is_set()
        assert state.is_single is False

    def test_push_chunk_queues_data(self):
        state = RequestState("req-1", time.time())
        state.push_chunk(b64_encode(b"chunk1"))
        assert not state.chunk_queue.empty()
        assert state.chunk_queue.get_nowait() == b"chunk1"

    def test_push_chunk_returns_length(self):
        state = RequestState("req-1", time.time())
        length = state.push_chunk(b64_encode(b"12345"))
        assert length == 5

    def test_multiple_chunks_preserve_order(self):
        state = RequestState("req-1", time.time())
        state.push_chunk(b64_encode(b"first"))
        state.push_chunk(b64_encode(b"second"))
        state.push_chunk(b64_encode(b"third"))

        assert state.chunk_queue.get_nowait() == b"first"
        assert state.chunk_queue.get_nowait() == b"second"
        assert state.chunk_queue.get_nowait() == b"third"

    def test_end_stream_pushes_sentinel(self):
        state = RequestState("req-1", time.time())
        state.end_stream()
        assert state.chunk_queue.get_nowait() is None

    def test_chunks_then_sentinel(self):
        state = RequestState("req-1", time.time())
        state.push_chunk(b64_encode(b"data"))
        state.end_stream()
        assert state.chunk_queue.get_nowait() == b"data"
        assert state.chunk_queue.get_nowait() is None


class TestWaitForHeaders:
    """Tests for blocking header wait."""

    def test_wait_returns_true_when_set(self):
        state = RequestState("req-1", time.time())
        state.headers_event.set()
        assert state.wait_for_headers(timeout=1.0) is True

    def test_wait_returns_false_on_timeout(self):
        state = RequestState("req-1", time.time())
        assert state.wait_for_headers(timeout=0.05) is False

    def test_wait_unblocks_from_another_thread(self):
        state = RequestState("req-1", time.time())

        def setter():
            time.sleep(0.05)
            state.set_single_response(200, {}, b64_encode(b"OK"))

        threading.Thread(target=setter, daemon=True).start()
        assert state.wait_for_headers(timeout=2.0) is True
        assert state.body == b"OK"


class TestFilteredHeaders:
    """Tests for response header filtering."""

    def test_strips_content_length(self):
        state = RequestState("req-1", time.time())
        state.headers = {"Content-Length": "42", "X-Custom": "yes"}
        filtered = state.get_filtered_headers()
        assert "Content-Length" not in filtered
        assert filtered["X-Custom"] == "yes"

    def test_strips_transfer_encoding(self):
        state = RequestState("req-1", time.time())
        state.headers = {"Transfer-Encoding": "chunked"}
        assert "Transfer-Encoding" not in state.get_filtered_headers()

    def test_strips_content_encoding(self):
        state = RequestState("req-1", time.time())
        state.headers = {"Content-Encoding": "gzip"}
        assert "Content-Encoding" not in state.get_filtered_headers()

    def test_case_insensitive_filtering(self):
        state = RequestState("req-1", time.time())
        state.headers = {"content-length": "10", "TRANSFER-ENCODING": "chunked"}
        filtered = state.get_filtered_headers()
        assert len(filtered) == 0

    def test_preserves_other_headers(self):
        state = RequestState("req-1", time.time())
        state.headers = {
            "X-Request-Id": "abc",
            "Content-Type": "application/json",
            "Content-Length": "100",
        }
        filtered = state.get_filtered_headers()
        assert "X-Request-Id" in filtered
        assert "Content-Type" in filtered
        assert "Content-Length" not in filtered


class TestLatency:
    """Tests for latency computation."""

    def test_compute_latency_positive(self):
        state = RequestState("req-1", time.time() - 0.1)
        latency = state.compute_latency_ms()
        assert latency >= 100.0  # At least 100ms

    def test_compute_latency_very_short(self):
        state = RequestState("req-1", time.time())
        latency = state.compute_latency_ms()
        assert latency >= 0
        assert latency < 100  # Should be near-zero
