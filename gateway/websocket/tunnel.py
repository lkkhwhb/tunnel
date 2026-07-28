"""
WebSocket tunnel handler.

Implements the tunnel registration protocol and the response multiplexer
that dispatches incoming response frames from tunnel clients to their
corresponding pending proxy requests.

Registration flow
-----------------
1. Client connects to ``/ws/tunnel?api_key=...&target_path=...&protocol_version=...``
2. Server validates protocol version, API key, and path parameter.
3. On success the tunnel is registered and enters the multiplexer loop.
4. On failure an ``{"error": "..."}`` frame is sent and the WS is closed.

Multiplexer
-----------
The loop reads JSON frames and dispatches by ``type``:

* ``pong``        — heartbeat acknowledgement (no-op).
* ``res_single``  — complete single-message response.
* ``res_start``   — streaming response header frame.
* ``res_chunk``   — streaming response body chunk.
* ``res_end``     — streaming response sentinel.
"""

import json

from flask import request

from gateway.config.settings import TUNNEL_TIMEOUT  # noqa: F401 — reserved for future use
from gateway.protocol.constants import (
    PROTOCOL_VERSION,
    MSG_PONG,
    MSG_RES_SINGLE,
    MSG_RES_START,
    MSG_RES_CHUNK,
    MSG_RES_END,
)
from gateway.utils.auth import verify_api_key, AuthError
from gateway import services as svc
from gateway.utils.log import get_logger

logger = get_logger()


def register_tunnel_handler(sock) -> None:
    """
    Register the ``/ws/tunnel`` WebSocket endpoint on the given Sock extension.

    This function is called by the app factory after the ``Sock`` extension
    has been initialized with the Flask app.

    Args:
        sock: The ``flask_sock.Sock`` instance.
    """

    @sock.route("/ws/tunnel")
    def tunnel_ws(ws):
        """
        Handle a tunnel client WebSocket connection.

        Performs authentication, registers the tunnel, and enters the
        multiplexer loop that dispatches response frames to pending
        proxy requests.
        """
        api_key = request.args.get("api_key")
        target_path = request.args.get("target_path")
        protocol_version = request.args.get("protocol_version")
        client_ip = request.remote_addr

        # ---- Validate Protocol Version ----
        if not protocol_version or protocol_version != PROTOCOL_VERSION:
            logger.warning(
                f"Registration failed from {client_ip}: "
                f"Incompatible protocol version {protocol_version}"
            )
            ws.send(json.dumps({
                "error": (
                    f"Incompatible protocol version. "
                    f"Server requires {PROTOCOL_VERSION}"
                ),
            }))
            return

        # ---- API Key Authentication ----
        try:
            verify_api_key(api_key)
        except AuthError as e:
            logger.warning(f"Auth failed for {client_ip}: {e.log_detail}")
            ws.send(json.dumps({"error": e.client_message}))
            return

        # ---- Validate Required Parameters ----
        if not target_path:
            logger.warning(
                f"Registration failed from {client_ip}: "
                f"Missing target_path"
            )
            ws.send(json.dumps({"error": "Missing target_path"}))
            return

        if not target_path.startswith("/"):
            target_path = "/" + target_path

        # ---- Register Tunnel (prevents duplicates) ----
        tunnel = svc.tunnel_manager.register(target_path, ws, client_ip)
        if tunnel is None:
            logger.warning(
                f"Duplicate registration attempt for "
                f"{target_path} from {client_ip}"
            )
            ws.send(json.dumps({
                "error": f"Tunnel path {target_path} is already in use.",
            }))
            return

        logger.info(
            f"Tunnel secured & registered: {target_path} by {client_ip}"
        )

        # ---- Multiplexer Loop ----
        try:
            while True:
                data = ws.receive()
                if data is None:
                    break

                # Update heartbeat timestamp
                svc.tunnel_manager.touch(target_path)

                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    logger.warning(
                        f"Received invalid JSON from {target_path}"
                    )
                    continue

                msg_type = payload.get("type")

                # Heartbeat acknowledgement — nothing to do
                if msg_type == MSG_PONG:
                    continue

                req_id = payload.get("req_id")
                if not req_id:
                    continue

                req_state = svc.request_manager.get(req_id)
                if not req_state:
                    continue

                # ---- Dispatch by Message Type ----

                if msg_type == MSG_RES_SINGLE:
                    body_len = req_state.set_single_response(
                        payload.get("status", 200),
                        payload.get("headers", {}),
                        payload.get("body", ""),
                    )
                    tunnel.record_download(body_len)
                    svc.server_stats.record_download(body_len)

                elif msg_type == MSG_RES_START:
                    req_state.set_streaming_start(
                        payload.get("status", 200),
                        payload.get("headers", {}),
                    )

                elif msg_type == MSG_RES_CHUNK:
                    chunk_len = req_state.push_chunk(
                        payload.get("data", ""),
                    )
                    tunnel.record_download(chunk_len)
                    svc.server_stats.record_download(chunk_len)

                elif msg_type == MSG_RES_END:
                    req_state.end_stream()

        except Exception as e:
            logger.error(f"Tunnel WS Error [{target_path}]: {e}")
        finally:
            svc.tunnel_manager.unregister(target_path, ws)
