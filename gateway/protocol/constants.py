"""
Protocol constants and message type definitions.

Centralizes all WebSocket message types and version identifiers
to eliminate scattered string literals across the codebase.
"""

# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Heartbeat Message Types
# ---------------------------------------------------------------------------
MSG_PING = "ping"
MSG_PONG = "pong"

# ---------------------------------------------------------------------------
# Request Message Types  (Server → Tunnel Client)
# ---------------------------------------------------------------------------
MSG_REQ_SINGLE = "req_single"
MSG_REQ_START = "req_start"
MSG_REQ_CHUNK = "req_chunk"
MSG_REQ_END = "req_end"

# ---------------------------------------------------------------------------
# Response Message Types  (Tunnel Client → Server)
# ---------------------------------------------------------------------------
MSG_RES_SINGLE = "res_single"
MSG_RES_START = "res_start"
MSG_RES_CHUNK = "res_chunk"
MSG_RES_END = "res_end"
