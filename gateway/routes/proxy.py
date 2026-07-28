"""
Proxy route handler  (dual-mode: single-message and streaming).

Implements the catch-all HTTP proxy that forwards incoming requests
through WebSocket tunnels to local client SDKs.  The protocol used
for each request is determined automatically:

* **Single-message mode** — for requests smaller than the streaming
  threshold.  The entire body is base64-encoded into one JSON frame.
* **Streaming mode** — for large or chunked-transfer-encoded requests.
  The body is split into base64-encoded chunks and sent as a sequence
  of ``req_start`` → ``req_chunk`` (×N) → ``req_end`` frames.
"""

import uuid
import time
import queue

from flask import Blueprint, Response, request, abort

from gateway.config.settings import (
    TUNNEL_TIMEOUT,
    STREAMING_THRESHOLD_BYTES,
    CHUNK_SIZE,
)
from gateway.protocol.messages import (
    build_req_single,
    build_req_start,
    build_req_chunk,
    build_req_end,
)
from gateway import services as svc
from gateway.utils.log import get_logger

logger = get_logger()

proxy_bp = Blueprint("proxy", __name__)


@proxy_bp.route(
    "/",
    defaults={"path": ""},
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
@proxy_bp.route(
    "/<path:path>",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
def catch_all_proxy(path):
    """
    Forward an incoming HTTP request to the matching tunnel client.

    Supports both single-message and streaming protocols depending on
    the request body size and transfer encoding.
    """
    # Guard: never shadow admin, wake, or web UI routes
    if (
        path.startswith("admin/")
        or path == "admin"
        or path == "wake"
        or path == "index.html"
        or path == "dashboard"
        or path.startswith("static/")
        or path == "favicon.ico"
    ):
        return abort(404)

    req_id = str(uuid.uuid4())
    start_time = time.time()
    full_path = "/" + path if path else "/"

    # ------------------------------------------------------------------ #
    # 1. Longest Prefix Match
    # ------------------------------------------------------------------ #
    matched_tunnel_path, tunnel = svc.tunnel_manager.find_longest_match(full_path)

    if not matched_tunnel_path:
        return Response(
            "No active tunnel registered for this endpoint.", status=404
        )

    # ------------------------------------------------------------------ #
    # 2. Update Global Stats
    # ------------------------------------------------------------------ #
    svc.server_stats.record_request_start()

    subpath = full_path[len(matched_tunnel_path):]
    if not subpath.startswith("/"):
        subpath = "/" + subpath

    headers = dict(request.headers)
    headers.pop("Host", None)

    req_state = svc.request_manager.create(req_id, start_time)

    content_length = request.headers.get("Content-Length", type=int)
    is_chunked = (
        request.headers.get("Transfer-Encoding", "").lower() == "chunked"
    )
    use_streaming = is_chunked or (
        content_length is not None and content_length > STREAMING_THRESHOLD_BYTES
    )

    generator_started = False
    cleanup_done = False

    method = request.method

    def do_cleanup():
        """Guarantees cleanup of pending requests and active request tracking."""
        nonlocal cleanup_done
        if not cleanup_done:
            cleanup_done = True
            svc.request_manager.remove(req_id)

            latency = req_state.compute_latency_ms()
            svc.server_stats.record_request_end(latency)

            logger.info(
                f"Request {req_id} completed in {latency:.2f}ms "
                f"[{method} {full_path}]"
            )

    try:
        query_string = request.query_string.decode("utf-8")

        if not use_streaming:
            # ---- FAST PATH: Single Message ----
            body_bytes = request.get_data()
            body_len = len(body_bytes)

            # Record upload stats
            if tunnel:
                tunnel.record_upload(body_len)
            svc.server_stats.record_upload(body_len)

            tunnel.send(
                build_req_single(
                    req_id, request.method, subpath, query_string,
                    headers, body_bytes,
                )
            )
        else:
            # ---- SLOW PATH: Chunked Streaming ----
            tunnel.send(
                build_req_start(
                    req_id, request.method, subpath, query_string, headers,
                )
            )

            while True:
                chunk = request.stream.read(CHUNK_SIZE)
                if not chunk:
                    break

                chunk_len = len(chunk)
                if tunnel:
                    tunnel.record_upload(chunk_len)
                svc.server_stats.record_upload(chunk_len)

                tunnel.send(build_req_chunk(req_id, chunk))

            tunnel.send(build_req_end(req_id))

        # ------------------------------------------------------------------ #
        # 3. Wait for Client Response Headers
        # ------------------------------------------------------------------ #
        if not req_state.wait_for_headers(timeout=TUNNEL_TIMEOUT):
            logger.warning(
                f"Timeout waiting for tunnel response on req_id: {req_id}"
            )
            return Response(
                "Gateway Timeout: The local client did not respond in time.",
                status=504,
            )

        resp_headers = req_state.get_filtered_headers()

        # ------------------------------------------------------------------ #
        # 4. Return Response (Dual Mode)
        # ------------------------------------------------------------------ #
        if req_state.is_single:
            return Response(
                req_state.body, status=req_state.status, headers=resp_headers,
            )
        else:
            generator_started = True

            def generate_response():
                try:
                    while True:
                        try:
                            chunk = req_state.chunk_queue.get(
                                timeout=TUNNEL_TIMEOUT
                            )
                            if chunk is None:
                                break
                            yield chunk
                        except queue.Empty:
                            logger.warning(
                                f"Queue timeout reading chunk for {req_id}"
                            )
                            break
                finally:
                    do_cleanup()

            return Response(
                generate_response(),
                status=req_state.status,
                headers=resp_headers,
            )

    except Exception as e:
        logger.error(f"Proxy routing error on req_id {req_id}: {e}")
        return Response(f"Internal gateway error: {e}", status=502)
    finally:
        # If we returned a streaming generator, cleanup happens in the
        # generator's finally block.  Otherwise (single response or error)
        # we clean up immediately here.
        if not generator_started:
            do_cleanup()
