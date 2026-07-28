"""
Shared test fixtures and helpers for the Tunnel Gateway test suite.

Provides:
- MockWebSocket:    Thread-safe mock WebSocket with message capture/injection.
- AutoResponder:    Background thread that auto-responds to proxy requests.
- App / client / service fixtures for integration tests.
"""

import os
import json
import time
import queue
import threading
import pytest

# Ensure TUNNEL_API_KEY is set before importing settings so tests don't fail on startup
os.environ.setdefault("TUNNEL_API_KEY", "test-api-key-12345")

from gateway.app import create_app
from gateway import services as svc
from gateway.config.settings import TUNNEL_API_KEY
from gateway.utils.encoding import b64_encode


# =========================================================================
# Mock WebSocket
# =========================================================================

class MockWebSocket:
    """
    Thread-safe mock WebSocket for testing tunnel connections.

    Captures messages sent by the server (``send()``) into a queue and
    allows tests to inject messages as if the client sent them (``inject()``).
    """

    def __init__(self):
        self._sent_queue: queue.Queue = queue.Queue()
        self._incoming_queue: queue.Queue = queue.Queue()
        self._sent_history: list[str] = []
        self._lock = threading.Lock()
        self.closed = False

    def send(self, data: str) -> None:
        """Capture a message sent by the server."""
        with self._lock:
            self._sent_history.append(data)
        self._sent_queue.put(data)

    def receive(self, timeout: float = 5.0):
        """Return the next message injected via ``inject()``, or ``None``."""
        try:
            return self._incoming_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        self.closed = True

    # ---- Test Helpers ----

    def get_sent(self, timeout: float = 2.0) -> str | None:
        """Block until the server sends a message, or return ``None``."""
        try:
            return self._sent_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_sent_parsed(self, timeout: float = 2.0) -> dict | None:
        """Like ``get_sent`` but JSON-parsed."""
        raw = self.get_sent(timeout)
        return json.loads(raw) if raw else None

    def get_all_sent(self) -> list[str]:
        """Return a copy of every message sent so far (from history)."""
        with self._lock:
            return list(self._sent_history)

    def drain_sent(self) -> list[str]:
        """Drain and return all queued sent messages."""
        msgs = []
        while True:
            try:
                msgs.append(self._sent_queue.get_nowait())
            except queue.Empty:
                break
        return msgs

    def inject(self, data: str) -> None:
        """Inject a message as if the tunnel client sent it."""
        self._incoming_queue.put(data)

    def inject_json(self, obj: dict) -> None:
        """Inject a JSON-serialized message."""
        self._incoming_queue.put(json.dumps(obj))

    @property
    def sent_count(self) -> int:
        with self._lock:
            return len(self._sent_history)


# =========================================================================
# Auto-Responder
# =========================================================================

class AutoResponder:
    """
    Background thread that watches a MockWebSocket for proxy request frames
    and automatically injects responses into the corresponding RequestState.

    This simulates a tunnel client SDK that immediately responds to every
    forwarded request, allowing the Flask test client to complete its
    synchronous HTTP call without blocking.
    """

    def __init__(
        self,
        mock_ws: MockWebSocket,
        tunnel,
        status: int = 200,
        headers: dict | None = None,
        body: bytes = b"OK",
        streaming: bool = False,
        chunks: list[bytes] | None = None,
    ):
        self.mock_ws = mock_ws
        self.tunnel = tunnel
        self.status = status
        self.headers = headers or {"Content-Type": "text/plain"}
        self.body = body
        self.streaming = streaming
        self.chunks = chunks or []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._captured: list[dict] = []

    def start(self) -> "AutoResponder":
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    @property
    def captured_requests(self) -> list[dict]:
        """All request payloads captured by this responder."""
        return list(self._captured)

    def _run(self) -> None:
        while not self._stop.is_set():
            raw = self.mock_ws.get_sent(timeout=0.3)
            if raw is None:
                continue

            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = payload.get("type")
            req_id = payload.get("req_id")

            if not req_id:
                continue  # ping or other non-request frame

            if msg_type == "req_single":
                self._captured.append(payload)
                self._respond(req_id)

            elif msg_type == "req_start":
                self._captured.append(payload)
                self._drain_stream(req_id)
                self._respond(req_id)

    def _respond(self, req_id: str) -> None:
        """Inject a response into the pending RequestState."""
        req_state = svc.request_manager.get(req_id)
        if not req_state:
            return

        if self.streaming:
            req_state.set_streaming_start(self.status, self.headers)
            for chunk in self.chunks:
                chunk_len = req_state.push_chunk(b64_encode(chunk))
                self.tunnel.record_download(chunk_len)
                svc.server_stats.record_download(chunk_len)
            req_state.end_stream()
        else:
            body_len = req_state.set_single_response(
                self.status, self.headers, b64_encode(self.body)
            )
            self.tunnel.record_download(body_len)
            svc.server_stats.record_download(body_len)

    def _drain_stream(self, req_id: str) -> None:
        """Drain ``req_chunk`` / ``req_end`` frames for a streaming request."""
        while not self._stop.is_set():
            raw = self.mock_ws.get_sent(timeout=1.0)
            if raw is None:
                break
            payload = json.loads(raw)
            if (
                payload.get("type") == "req_end"
                and payload.get("req_id") == req_id
            ):
                break


# =========================================================================
# Pytest Fixtures
# =========================================================================

@pytest.fixture
def app():
    """Create a fresh Flask application with all services initialized."""
    application = create_app()
    yield application


@pytest.fixture
def client(app):
    """Flask test client wired to the test app."""
    return app.test_client()


@pytest.fixture
def mock_ws():
    """Fresh MockWebSocket instance."""
    return MockWebSocket()


@pytest.fixture
def registered_tunnel(app, mock_ws):
    """
    Register a tunnel at ``/test`` and yield ``(tunnel, mock_ws)``.

    The tunnel is automatically cleaned up after the test.
    """
    tunnel = svc.tunnel_manager.register("/test", mock_ws, "127.0.0.1")
    yield tunnel, mock_ws
    svc.tunnel_manager.unregister("/test")


@pytest.fixture
def tunnel_responder(app, mock_ws):
    """
    Register a tunnel at ``/test`` with an auto-responder that replies
    HTTP 200 with body ``b"OK"`` to every forwarded request.

    Yields ``(tunnel, mock_ws, responder)``.
    """
    tunnel = svc.tunnel_manager.register("/test", mock_ws, "127.0.0.1")
    responder = AutoResponder(mock_ws, tunnel).start()
    yield tunnel, mock_ws, responder
    responder.stop()
    svc.tunnel_manager.unregister("/test")


@pytest.fixture
def streaming_responder(app):
    """
    Register a tunnel at ``/test`` with a streaming auto-responder.

    Yields ``(tunnel, mock_ws, responder)``.
    """
    ws = MockWebSocket()
    tunnel = svc.tunnel_manager.register("/test", ws, "127.0.0.1")
    responder = AutoResponder(
        ws, tunnel,
        streaming=True,
        chunks=[b"chunk1", b"chunk2", b"chunk3"],
        headers={"Content-Type": "application/octet-stream"},
    ).start()
    yield tunnel, ws, responder
    responder.stop()
    svc.tunnel_manager.unregister("/test")


@pytest.fixture
def valid_api_key():
    """Valid API key for testing."""
    return TUNNEL_API_KEY
