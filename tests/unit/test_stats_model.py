"""
Unit tests for gateway.models.stats.ServerStats.

Verifies thread-safe counting, snapshot consistency, and latency averaging.
"""

import time
import threading

from gateway.models.stats import ServerStats


class TestConstruction:
    """Verify initial state."""

    def test_initial_values(self):
        stats = ServerStats()
        assert stats.total_requests == 0
        assert stats.active_requests == 0
        assert stats.bytes_uploaded == 0
        assert stats.bytes_downloaded == 0
        assert stats.total_latency_ms == 0.0
        assert stats.started_at > 0

    def test_started_at_is_recent(self):
        before = time.time()
        stats = ServerStats()
        assert stats.started_at >= before


class TestRequestLifecycle:
    """Tests for request start/end counters."""

    def test_record_request_start(self):
        stats = ServerStats()
        stats.record_request_start()
        assert stats.total_requests == 1
        assert stats.active_requests == 1

    def test_multiple_starts(self):
        stats = ServerStats()
        for _ in range(5):
            stats.record_request_start()
        assert stats.total_requests == 5
        assert stats.active_requests == 5

    def test_record_request_end(self):
        stats = ServerStats()
        stats.record_request_start()
        stats.record_request_end(100.0)
        assert stats.active_requests == 0
        assert stats.total_latency_ms == 100.0

    def test_active_never_negative(self):
        stats = ServerStats()
        stats.record_request_end(10.0)
        assert stats.active_requests == 0

    def test_latency_accumulates(self):
        stats = ServerStats()
        stats.record_request_start()
        stats.record_request_end(50.0)
        stats.record_request_start()
        stats.record_request_end(150.0)
        assert stats.total_latency_ms == 200.0


class TestByteCounters:
    """Tests for upload/download byte counters."""

    def test_record_upload(self):
        stats = ServerStats()
        stats.record_upload(1024)
        stats.record_upload(2048)
        assert stats.bytes_uploaded == 3072

    def test_record_download(self):
        stats = ServerStats()
        stats.record_download(512)
        assert stats.bytes_downloaded == 512

    def test_zero_bytes(self):
        stats = ServerStats()
        stats.record_upload(0)
        stats.record_download(0)
        assert stats.bytes_uploaded == 0
        assert stats.bytes_downloaded == 0


class TestSnapshot:
    """Tests for the snapshot method."""

    def test_snapshot_keys(self):
        stats = ServerStats()
        snap = stats.snapshot()
        expected_keys = {
            "started_at", "uptime_seconds", "total_requests",
            "active_requests", "bytes_uploaded", "bytes_downloaded",
            "total_bytes_transferred", "average_latency_ms",
        }
        assert set(snap.keys()) == expected_keys

    def test_snapshot_reflects_state(self):
        stats = ServerStats()
        stats.record_request_start()
        stats.record_upload(100)
        stats.record_download(200)

        snap = stats.snapshot()
        assert snap["total_requests"] == 1
        assert snap["active_requests"] == 1
        assert snap["bytes_uploaded"] == 100
        assert snap["bytes_downloaded"] == 200
        assert snap["total_bytes_transferred"] == 300

    def test_average_latency_zero_requests(self):
        stats = ServerStats()
        snap = stats.snapshot()
        assert snap["average_latency_ms"] == 0.0

    def test_average_latency_computed(self):
        stats = ServerStats()
        stats.record_request_start()
        stats.record_request_end(100.0)
        stats.record_request_start()
        stats.record_request_end(200.0)

        snap = stats.snapshot()
        assert snap["average_latency_ms"] == 150.0

    def test_uptime_positive(self):
        stats = ServerStats()
        time.sleep(0.01)
        snap = stats.snapshot()
        assert snap["uptime_seconds"] >= 0.01


class TestThreadSafety:
    """Verify that concurrent stat updates don't corrupt data."""

    def test_concurrent_increments(self):
        stats = ServerStats()
        barrier = threading.Barrier(20)

        def worker():
            barrier.wait()
            for _ in range(100):
                stats.record_request_start()
                stats.record_upload(10)
                stats.record_download(5)
                stats.record_request_end(1.0)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        snap = stats.snapshot()
        assert snap["total_requests"] == 2000
        assert snap["active_requests"] == 0
        assert snap["bytes_uploaded"] == 20000
        assert snap["bytes_downloaded"] == 10000
        assert stats.total_latency_ms == 2000.0
        assert snap["average_latency_ms"] == 1.0
