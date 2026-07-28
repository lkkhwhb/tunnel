"""
Dispatches incoming WebSocket messages to the local HTTP server.
"""
import threading
import queue
import time
import httpx
import logging
import urllib.parse
from typing import Dict, Any, Callable

from tunnel_sdk.protocol import (
    decode_base64, decode_payload, build_res_single, build_res_start, 
    build_res_chunk, build_res_end
)

logger = logging.getLogger("tunnel_sdk.dispatcher")

class RequestDispatcher:
    def __init__(self, local_url: str, ws_send_func: Callable[[str], None], stats, events):
        self.local_url = local_url.rstrip("/")
        self.ws_send_func = ws_send_func
        self.stats = stats
        self.events = events
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=100)
        self.http_client = httpx.Client(timeout=None, limits=limits)
        self.executor = threading.concurrent.futures.ThreadPoolExecutor(max_workers=50) if hasattr(threading, 'concurrent') else None
        
        # In Python standard library, ThreadPoolExecutor is in concurrent.futures
        import concurrent.futures
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=50)
        
        # req_id -> Queue for streaming chunks
        self.streaming_queues: Dict[str, queue.Queue] = {}
        # req_id -> StopEvent to signal end of stream
        self.streaming_events: Dict[str, threading.Event] = {}

    def shutdown(self):
        self.executor.shutdown(wait=False)
        self.http_client.close()

    def dispatch_single(self, msg: Dict[str, Any]):
        self.executor.submit(self._handle_single, msg)

    def dispatch_start(self, msg: Dict[str, Any]):
        req_id = msg["req_id"]
        q = queue.Queue(maxsize=100)
        ev = threading.Event()
        self.streaming_queues[req_id] = q
        self.streaming_events[req_id] = ev
        self.executor.submit(self._handle_stream, msg, q, ev)

    def dispatch_chunk(self, msg: Dict[str, Any]):
        req_id = msg["req_id"]
        if req_id in self.streaming_queues:
            self.streaming_queues[req_id].put(
                decode_payload(msg["data"], compressed=msg.get("compressed", False))
            )

    def dispatch_end(self, msg: Dict[str, Any]):
        req_id = msg["req_id"]
        if req_id in self.streaming_events:
            self.streaming_events[req_id].set()

    def _build_url(self, subpath: str, query: str) -> str:
        url = self.local_url + subpath
        if query:
            url += "?" + query
        return url

    def _filter_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        # Filter out headers that shouldn't be forwarded to local
        filtered = {}
        for k, v in headers.items():
            k_lower = k.lower()
            if k_lower not in ("host", "connection", "upgrade"):
                filtered[k] = v
        return filtered

    def _handle_single(self, msg: Dict[str, Any]):
        req_id = msg["req_id"]
        try:
            self.stats.inc_active_requests()
            self.events.emit("on_request_start", req_id)
            
            url = self._build_url(msg["subpath"], msg["query"])
            headers = self._filter_headers(msg.get("headers", {}))
            body_bytes = decode_payload(msg.get("body", ""), compressed=msg.get("compressed", False)) if msg.get("body") else None
            
            if body_bytes:
                self.stats.add_bytes_downloaded(len(body_bytes))

            for attempt in range(6):
                try:
                    resp = self.http_client.request(
                        method=msg["method"],
                        url=url,
                        headers=headers,
                        content=body_bytes,
                        follow_redirects=False
                    )
                    break
                except (httpx.HTTPError, OSError) as e:
                    if attempt == 5:
                        raise
                    time.sleep(0.5)
            
            resp_body = resp.content
            self.stats.add_bytes_uploaded(len(resp_body))
            
            res_msg = build_res_single(
                req_id=req_id,
                status=resp.status_code,
                headers=dict(resp.headers),
                body=resp_body
            )
            self.ws_send_func(res_msg)
            
        except Exception as e:
            logger.error(f"Error handling single request {req_id}: {e}")
            res_msg = build_res_single(req_id, 502, {}, str(e).encode('utf-8'))
            self.ws_send_func(res_msg)
        finally:
            self.stats.dec_active_requests()
            self.events.emit("on_request_end", req_id)

    def _handle_stream(self, msg: Dict[str, Any], q: queue.Queue, ev: threading.Event):
        req_id = msg["req_id"]
        try:
            self.stats.inc_active_requests()
            self.events.emit("on_request_start", req_id)
            
            url = self._build_url(msg["subpath"], msg["query"])
            headers = self._filter_headers(msg.get("headers", {}))

            def chunk_generator():
                while True:
                    try:
                        chunk = q.get(timeout=0.1)
                        self.stats.add_bytes_downloaded(len(chunk))
                        yield chunk
                    except queue.Empty:
                        if ev.is_set() and q.empty():
                            break
                        continue

            req = self.http_client.build_request(
                method=msg["method"],
                url=url,
                headers=headers,
                content=chunk_generator()
            )
            
            for attempt in range(6):
                try:
                    resp = self.http_client.send(req, stream=True, follow_redirects=False)
                    break
                except (httpx.HTTPError, OSError) as e:
                    if attempt == 5:
                        raise
                    time.sleep(0.5)
            
            # Send res_start
            start_msg = build_res_start(
                req_id=req_id,
                status=resp.status_code,
                headers=dict(resp.headers)
            )
            self.ws_send_func(start_msg)
            
            # Send chunks
            for chunk in resp.iter_bytes(chunk_size=32768):
                if chunk:
                    self.stats.add_bytes_uploaded(len(chunk))
                    self.ws_send_func(build_res_chunk(req_id, chunk))
                    
            # Send res_end
            self.ws_send_func(build_res_end(req_id))
            resp.close()

        except Exception as e:
            logger.error(f"Error handling streaming request {req_id}: {e}")
            self.ws_send_func(build_res_single(req_id, 502, {}, str(e).encode('utf-8')))
        finally:
            self.stats.dec_active_requests()
            self.events.emit("on_request_end", req_id)
            self.streaming_queues.pop(req_id, None)
            self.streaming_events.pop(req_id, None)
