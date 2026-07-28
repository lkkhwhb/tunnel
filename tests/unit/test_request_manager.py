"""
Unit tests for gateway.services.request_manager.RequestManager.

Verifies creation, lookup, removal, and thread safety.
"""

import time
import threading

from gateway.services.request_manager import RequestManager


class TestCreate:
    """Tests for request creation."""

    def test_create_returns_state(self):
        mgr = RequestManager()
        state = mgr.create("req-1", time.time())
        assert state is not None
        assert state.req_id == "req-1"

    def test_create_multiple(self):
        mgr = RequestManager()
        s1 = mgr.create("req-1", time.time())
        s2 = mgr.create("req-2", time.time())
        assert s1.req_id != s2.req_id


class TestGet:
    """Tests for request lookup."""

    def test_get_existing(self):
        mgr = RequestManager()
        mgr.create("req-1", time.time())
        state = mgr.get("req-1")
        assert state is not None
        assert state.req_id == "req-1"

    def test_get_nonexistent_returns_none(self):
        mgr = RequestManager()
        assert mgr.get("nope") is None

    def test_get_after_removal(self):
        mgr = RequestManager()
        mgr.create("req-1", time.time())
        mgr.remove("req-1")
        assert mgr.get("req-1") is None


class TestRemove:
    """Tests for request removal."""

    def test_remove_existing(self):
        mgr = RequestManager()
        mgr.create("req-1", time.time())
        mgr.remove("req-1")
        assert mgr.get("req-1") is None

    def test_remove_nonexistent_is_safe(self):
        mgr = RequestManager()
        mgr.remove("nope")  # Should not raise

    def test_remove_idempotent(self):
        mgr = RequestManager()
        mgr.create("req-1", time.time())
        mgr.remove("req-1")
        mgr.remove("req-1")  # Second remove is a no-op


class TestThreadSafety:
    """Stress test for concurrent operations."""

    def test_concurrent_create_get_remove(self):
        mgr = RequestManager()
        barrier = threading.Barrier(20)

        def worker(i):
            barrier.wait()
            req_id = f"req-{i}"
            mgr.create(req_id, time.time())
            state = mgr.get(req_id)
            assert state is not None
            assert state.req_id == req_id
            mgr.remove(req_id)
            assert mgr.get(req_id) is None

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
