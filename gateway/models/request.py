"""
RequestState model.

Represents the state of an in-flight proxied HTTP request, tracking
response headers, body data, and providing synchronization between the
proxy route (which waits for the response) and the WebSocket multiplexer
(which receives response data from the tunnel client).
"""

import queue
import threading
import time

from gateway.utils.encoding import b64_decode, decode_payload


class RequestState:
    """
    Tracks the full lifecycle of a single proxied HTTP request.

    Synchronization
    ---------------
    * ``headers_event`` — a :class:`threading.Event` that the proxy route
      blocks on while waiting for response headers from the tunnel client.
    * ``chunk_queue`` — a :class:`queue.Queue` used to stream response
      chunks from the multiplexer to the proxy generator.
    """

    __slots__ = (
        "req_id",
        "start_time",
        "headers_event",
        "chunk_queue",
        "status",
        "headers",
        "is_single",
        "body",
    )

    def __init__(self, req_id: str, start_time: float):
        self.req_id = req_id
        self.start_time = start_time
        self.headers_event = threading.Event()
        self.chunk_queue: queue.Queue = queue.Queue()
        self.status: int = 500
        self.headers: dict = {}
        self.is_single: bool = False
        self.body: bytes = b""

    # ------------------------------------------------------------------
    # Response Application  (called by the WebSocket multiplexer)
    # ------------------------------------------------------------------

    def set_single_response(self, status: int, headers: dict, encoded_body: str, compressed: bool = False) -> int:
        """
        Apply a complete single-message response from the tunnel client.

        Args:
            status:       HTTP status code.
            headers:      Response headers dict.
            encoded_body: Base64-encoded response body string.
            compressed:   Whether the body was compressed with zlib.

        Returns:
            The decoded body length in bytes (for stats tracking).
        """
        self.status = status
        self.headers = headers
        body_bytes = decode_payload(encoded_body, compressed=compressed)
        self.body = body_bytes
        self.is_single = True
        self.headers_event.set()
        return len(body_bytes)

    def set_streaming_start(self, status: int, headers: dict) -> None:
        """
        Apply the initial streaming response metadata from the tunnel client.

        Signals the proxy route that headers are available so it can begin
        streaming the response body to the original HTTP caller.

        Args:
            status:  HTTP status code.
            headers: Response headers dict.
        """
        self.status = status
        self.headers = headers
        self.headers_event.set()

    def push_chunk(self, encoded_data: str, compressed: bool = False) -> int:
        """
        Enqueue a streaming response chunk from the tunnel client.

        Args:
            encoded_data: Base64-encoded chunk data string.
            compressed:   Whether the chunk was compressed with zlib.

        Returns:
            The decoded chunk length in bytes (for stats tracking).
        """
        chunk_bytes = decode_payload(encoded_data, compressed=compressed)
        self.chunk_queue.put(chunk_bytes)
        return len(chunk_bytes)

    def end_stream(self) -> None:
        """Signal the end of a streaming response by pushing a ``None`` sentinel."""
        self.chunk_queue.put(None)

    # ------------------------------------------------------------------
    # Proxy-side Helpers  (called by the proxy route)
    # ------------------------------------------------------------------

    def wait_for_headers(self, timeout: float) -> bool:
        """
        Block until response headers are received or *timeout* expires.

        Args:
            timeout: Maximum seconds to wait.

        Returns:
            ``True`` if headers were received, ``False`` on timeout.
        """
        return self.headers_event.wait(timeout=timeout)

    def get_filtered_headers(self) -> dict:
        """
        Return response headers with hop-by-hop headers removed.

        Strips ``content-length``, ``transfer-encoding``, and
        ``content-encoding`` to avoid conflicts with the proxy's own
        transfer handling.
        """
        return {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in ("content-length", "transfer-encoding", "content-encoding")
        }

    def compute_latency_ms(self) -> float:
        """Compute elapsed time since request creation in milliseconds."""
        return (time.time() - self.start_time) * 1000
