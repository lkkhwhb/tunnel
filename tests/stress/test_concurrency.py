"""
Stress and concurrency tests for system lifecycle and thread safety.

Verifies that concurrent tunnel registrations, disconnects, heartbeats,
and proxy routing operations do not cause race conditions, deadlocks,
or memory leaks.
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor

from gateway import services as svc
from tests.conftest import MockWebSocket, AutoResponder


class TestConcurrentRegistration:
    """Verify thread safety of tunnel registration under concurrent contention."""

    def test_concurrent_registration_same_path(self, app):
        """When 10 threads try to register the same path simultaneously, exactly 1 wins."""
        results = []
        sockets = [MockWebSocket() for _ in range(10)]
        barrier = threading.Barrier(10)

        def register_worker(idx):
            barrier.wait()
            tunnel = svc.tunnel_manager.register("/contested", sockets[idx], f"10.0.0.{idx}")
            results.append(tunnel)

        threads = [threading.Thread(target=register_worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        successful = [t for t in results if t is not None]
        assert len(successful) == 1, f"Expected exactly 1 successful registration, got {len(successful)}"
        assert svc.tunnel_manager.count() == 1
        svc.tunnel_manager.unregister("/contested")

    def test_concurrent_register_and_unregister(self, app):
        """Verify stability when registrations and removals happen concurrently."""
        stop_event = threading.Event()
        errors = []

        def register_loop():
            while not stop_event.is_set():
                try:
                    ws = MockWebSocket()
                    svc.tunnel_manager.register("/dynamic", ws, "10.0.0.1")
                    time.sleep(0.001)
                except Exception as e:
                    errors.append(e)

        def unregister_loop():
            while not stop_event.is_set():
                try:
                    svc.tunnel_manager.unregister("/dynamic")
                    time.sleep(0.001)
                except Exception as e:
                    errors.append(e)

        t1 = threading.Thread(target=register_loop)
        t2 = threading.Thread(target=unregister_loop)
        t1.start()
        t2.start()

        time.sleep(0.5)
        stop_event.set()
        t1.join(timeout=2)
        t2.join(timeout=2)

        assert not errors, f"Exceptions raised during concurrent register/unregister: {errors}"
        svc.tunnel_manager.unregister("/dynamic")


class TestConcurrentTrafficAndDisconnects:
    """Verify stability when tunnels disconnect while requests are in-flight."""

    def test_disconnect_during_active_requests(self, client, app):
        """Simulate a tunnel unregistering while HTTP requests are actively waiting."""
        ws = MockWebSocket()
        tunnel = svc.tunnel_manager.register("/unstable", ws, "127.0.0.1")
        
        # We start an auto-responder that replies slowly
        responder = AutoResponder(ws, tunnel).start()
        
        results = []
        def slow_client_request():
            try:
                resp = client.get("/unstable/slow")
                results.append(resp.status_code)
            except Exception as e:
                results.append(e)

        # Launch multiple requests in background threads
        threads = [threading.Thread(target=slow_client_request) for _ in range(5)]
        for t in threads:
            t.start()

        # Let requests hit the proxy and get queued
        time.sleep(0.05)
        
        # Forcefully unregister tunnel while requests might be processing
        svc.tunnel_manager.unregister("/unstable", ws=ws)
        responder.stop()

        for t in threads:
            t.join(timeout=5)

        # All threads should finish without deadlocking; status might be 200 (if finished early) or 504/502/404
        assert len(results) == 5
        for r in results:
            assert isinstance(r, int), f"Client request raised an unhandled exception: {r}"

        # Verify all request states are cleaned up
        snap = svc.server_stats.snapshot()
        assert snap["active_requests"] == 0

    def test_concurrent_stats_snapshots_under_load(self, client, tunnel_responder):
        """Verify admin status snapshots never crash or deadlock while traffic flows."""
        tunnel, mock_ws, responder = tunnel_responder
        stop_event = threading.Event()
        errors = []
        snapshots = []

        def snapshot_worker():
            while not stop_event.is_set():
                try:
                    snap = svc.server_stats.snapshot()
                    t_info = svc.tunnel_manager.get_tunnels_info()
                    snapshots.append((snap, t_info))
                    time.sleep(0.005)
                except Exception as e:
                    errors.append(e)

        snap_thread = threading.Thread(target=snapshot_worker)
        snap_thread.start()

        try:
            def traffic_worker(_):
                client.post("/test/traffic", data=b"some-data")

            with ThreadPoolExecutor(max_workers=10) as executor:
                executor.map(traffic_worker, range(30))
        finally:
            stop_event.set()
            snap_thread.join(timeout=2)

        assert not errors, f"Errors during concurrent snapshots: {errors}"
        assert len(snapshots) > 0
