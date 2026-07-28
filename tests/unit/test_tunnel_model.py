"""
Unit tests for gateway.models.tunnel.TunnelConnection.

Verifies construction, thread-safe send, heartbeat touch, stats recording,
and admin serialization.
"""

import time
import threading

from tests.conftest import MockWebSocket
from gateway.models.tunnel import TunnelConnection


class TestConstruction:
    """Verify initial state after construction."""

    def test_initial_state(self):
        ws = MockWebSocket()
        tunnel = TunnelConnection(ws, "10.0.0.1")

        assert tunnel.ws is ws
        assert tunnel.client_ip == "10.0.0.1"
        assert isinstance(tunnel.send_lock, type(threading.Lock()))
        assert tunnel.connected_at > 0
        assert tunnel.last_active > 0
        assert tunnel.requests_served == 0
        assert tunnel.bytes_uploaded == 0
        assert tunnel.bytes_downloaded == 0

    def test_timestamps_are_recent(self):
        before = time.time()
        tunnel = TunnelConnection(MockWebSocket(), "10.0.0.1")
        after = time.time()

        assert before <= tunnel.connected_at <= after
        assert before <= tunnel.last_active <= after


class TestSend:
    """Verify thread-safe message sending."""

    def test_send_delivers_message(self):
        ws = MockWebSocket()
        tunnel = TunnelConnection(ws, "10.0.0.1")
        tunnel.send('{"type": "ping"}')
        assert ws.get_sent() == '{"type": "ping"}'

    def test_send_acquires_lock(self):
        """Concurrent sends should not interleave."""
        ws = MockWebSocket()
        tunnel = TunnelConnection(ws, "10.0.0.1")
        results = []
        barrier = threading.Barrier(10)

        def sender(msg):
            barrier.wait()
            tunnel.send(msg)
            results.append(msg)

        threads = [
            threading.Thread(target=sender, args=(f"msg-{i}",))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert ws.sent_count == 10

    def test_send_multiple_messages(self):
        ws = MockWebSocket()
        tunnel = TunnelConnection(ws, "10.0.0.1")
        for i in range(5):
            tunnel.send(f"msg-{i}")
        assert ws.sent_count == 5


class TestTouch:
    """Verify heartbeat timestamp updates."""

    def test_touch_updates_last_active(self):
        tunnel = TunnelConnection(MockWebSocket(), "10.0.0.1")
        old = tunnel.last_active
        time.sleep(0.01)
        tunnel.touch()
        assert tunnel.last_active > old

    def test_touch_does_not_change_connected_at(self):
        tunnel = TunnelConnection(MockWebSocket(), "10.0.0.1")
        original = tunnel.connected_at
        tunnel.touch()
        assert tunnel.connected_at == original


class TestStats:
    """Verify per-tunnel statistics recording."""

    def test_record_upload(self):
        tunnel = TunnelConnection(MockWebSocket(), "10.0.0.1")
        tunnel.record_upload(100)
        tunnel.record_upload(200)
        assert tunnel.bytes_uploaded == 300

    def test_record_download(self):
        tunnel = TunnelConnection(MockWebSocket(), "10.0.0.1")
        tunnel.record_download(500)
        assert tunnel.bytes_downloaded == 500

    def test_increment_requests(self):
        tunnel = TunnelConnection(MockWebSocket(), "10.0.0.1")
        tunnel.increment_requests()
        tunnel.increment_requests()
        tunnel.increment_requests()
        assert tunnel.requests_served == 3

    def test_zero_byte_upload(self):
        tunnel = TunnelConnection(MockWebSocket(), "10.0.0.1")
        tunnel.record_upload(0)
        assert tunnel.bytes_uploaded == 0


class TestToInfoDict:
    """Verify admin API serialization."""

    def test_info_dict_keys(self):
        tunnel = TunnelConnection(MockWebSocket(), "192.168.1.5")
        info = tunnel.to_info_dict()
        expected_keys = {
            "client_ip", "uptime_seconds", "requests_served",
            "bytes_uploaded", "bytes_downloaded", "total_bytes_transferred",
        }
        assert set(info.keys()) == expected_keys

    def test_info_dict_values(self):
        tunnel = TunnelConnection(MockWebSocket(), "192.168.1.5")
        tunnel.record_upload(100)
        tunnel.record_download(200)
        tunnel.increment_requests()

        info = tunnel.to_info_dict()
        assert info["client_ip"] == "192.168.1.5"
        assert info["requests_served"] == 1
        assert info["bytes_uploaded"] == 100
        assert info["bytes_downloaded"] == 200
        assert info["total_bytes_transferred"] == 300

    def test_uptime_is_positive(self):
        tunnel = TunnelConnection(MockWebSocket(), "10.0.0.1")
        time.sleep(0.01)
        info = tunnel.to_info_dict()
        assert info["uptime_seconds"] >= 0.01
