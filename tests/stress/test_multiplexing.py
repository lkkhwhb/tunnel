"""
Stress and concurrency tests for request multiplexing.

Verifies that multiple concurrent HTTP requests forwarded over a single
WebSocket tunnel remain isolated, do not corrupt each other's payloads,
and can be completed out of order without deadlocks or state leakage.
"""

import time
import json
import random
import threading
from concurrent.futures import ThreadPoolExecutor

from gateway import services as svc
from gateway.utils.encoding import b64_encode, b64_decode
from tests.conftest import MockWebSocket, AutoResponder


class TestMultiplexedIsolation:
    """Verify isolation and ordering of concurrent requests over one tunnel."""

    def test_concurrent_requests_get_correct_responses(self, client, app):
        """Send 20 concurrent requests where the responder replies out of order."""
        ws = MockWebSocket()
        tunnel, _ = svc.tunnel_manager.register("/test", ws, "127.0.0.1")

        # We create a custom responder that replies with delay/random ordering
        stop_event = threading.Event()

        def custom_responder():
            while not stop_event.is_set():
                raw = ws.get_sent(timeout=0.1)
                if raw is None:
                    continue
                try:
                    payload = json.loads(raw)
                except Exception:
                    continue

                if payload.get("type") == "req_single":
                    req_id = payload["req_id"]
                    subpath = payload.get("subpath", "")
                    
                    # Simulate variable processing time to force out-of-order responses
                    def reply(rid, path):
                        time.sleep(random.uniform(0.01, 0.05))
                        state = svc.request_manager.get(rid)
                        if state:
                            resp_body = f"reply-for-{path}".encode()
                            state.set_single_response(200, {}, b64_encode(resp_body))

                    threading.Thread(target=reply, args=(req_id, subpath), daemon=True).start()

        t = threading.Thread(target=custom_responder, daemon=True)
        t.start()

        try:
            results = {}
            errors = []

            def make_request(idx):
                try:
                    path = f"/test/req-{idx}"
                    resp = client.get(path)
                    results[idx] = (resp.status_code, resp.data.decode())
                except Exception as e:
                    errors.append(e)

            with ThreadPoolExecutor(max_workers=10) as executor:
                executor.map(make_request, range(20))

            assert not errors, f"Errors occurred during concurrent requests: {errors}"
            assert len(results) == 20
            for idx, (status, body) in results.items():
                assert status == 200
                assert body == f"reply-for-/req-{idx}", f"Mismatch for request {idx}: got {body}"

        finally:
            stop_event.set()
            t.join(timeout=2)
            svc.tunnel_manager.unregister("/test")

    def test_interleaved_streaming_and_single_requests(self, client, app):
        """Verify that streaming requests and single messages can interleave safely."""
        ws = MockWebSocket()
        tunnel, _ = svc.tunnel_manager.register("/test", ws, "127.0.0.1")
        stop_event = threading.Event()

        def mixed_responder():
            while not stop_event.is_set():
                raw = ws.get_sent(timeout=0.1)
                if raw is None:
                    continue
                try:
                    payload = json.loads(raw)
                except Exception:
                    continue

                req_id = payload.get("req_id")
                subpath = payload.get("subpath", "")

                if subpath.startswith("/stream-"):
                    # For streaming, push chunks with slight delays
                    def stream_reply(rid):
                        state = svc.request_manager.get(rid)
                        if not state:
                            return
                        state.set_streaming_start(200, {"Content-Type": "text/plain"})
                        for c in (b"stream-1", b"stream-2", b"stream-3"):
                            time.sleep(0.01)
                            state.push_chunk(b64_encode(c))
                        state.end_stream()

                    threading.Thread(target=stream_reply, args=(req_id,), daemon=True).start()
                else:
                    state = svc.request_manager.get(req_id)
                    if state:
                        state.set_single_response(200, {}, b64_encode(b"single-ok"))

        t = threading.Thread(target=mixed_responder, daemon=True)
        t.start()

        try:
            results = {}

            def run_single(idx):
                resp = client.get(f"/test/single-{idx}")
                results[f"single-{idx}"] = resp.data.decode()

            def run_stream(idx):
                resp = client.get(f"/test/stream-{idx}")
                results[f"stream-{idx}"] = resp.data.decode()

            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = []
                for i in range(10):
                    futures.append(executor.submit(run_single, i))
                    futures.append(executor.submit(run_stream, i))
                for f in futures:
                    f.result()

            for i in range(10):
                assert results[f"single-{i}"] == "single-ok"
                assert results[f"stream-{i}"] == "stream-1stream-2stream-3"

        finally:
            stop_event.set()
            t.join(timeout=2)
            svc.tunnel_manager.unregister("/test")

    def test_high_volume_simultaneous_requests(self, client, tunnel_responder):
        """Stress test: 50 simultaneous single-message requests."""
        tunnel, mock_ws, responder = tunnel_responder
        results = []
        errors = []

        def worker(idx):
            try:
                resp = client.post("/test/echo", data=f"payload-{idx}".encode())
                results.append((resp.status_code, resp.data))
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=20) as executor:
            executor.map(worker, range(50))

        assert not errors
        assert len(results) == 50
        for status, data in results:
            assert status == 200
            assert data == b"OK"
        
        # Verify no requests leaked
        snap = svc.server_stats.snapshot()
        assert snap["active_requests"] == 0
        assert snap["total_requests"] >= 50
