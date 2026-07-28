"""
Protocol utilities for encoding, decoding, and parsing Tunnel Gateway messages.
"""
import base64
import json
from typing import Dict, Any, Optional

from tunnel_sdk.exceptions import ProtocolError

PROTOCOL_VERSION = "1.0"

def decode_base64(data: str) -> bytes:
    """Decodes a base64 string to bytes."""
    try:
        return base64.b64decode(data)
    except Exception as e:
        raise ProtocolError(f"Failed to decode base64 data: {e}")

def encode_base64(data: bytes) -> str:
    """Encodes bytes to a base64 string."""
    try:
        return base64.b64encode(data).decode('ascii')
    except Exception as e:
        raise ProtocolError(f"Failed to encode base64 data: {e}")

def parse_message(raw_msg: str) -> Dict[str, Any]:
    """Parses a raw WebSocket message string into a JSON dictionary."""
    try:
        return json.loads(raw_msg)
    except json.JSONDecodeError as e:
        raise ProtocolError(f"Invalid JSON in message: {e}")

def build_pong() -> str:
    return json.dumps({"type": "pong"})

def build_res_single(req_id: str, status: int, headers: Dict[str, str], body: bytes) -> str:
    return json.dumps({
        "type": "res_single",
        "req_id": req_id,
        "status": status,
        "headers": headers,
        "body": encode_base64(body)
    })

def build_res_start(req_id: str, status: int, headers: Dict[str, str]) -> str:
    return json.dumps({
        "type": "res_start",
        "req_id": req_id,
        "status": status,
        "headers": headers
    })

def build_res_chunk(req_id: str, chunk: bytes) -> str:
    return json.dumps({
        "type": "res_chunk",
        "req_id": req_id,
        "data": encode_base64(chunk)
    })

def build_res_end(req_id: str) -> str:
    return json.dumps({
        "type": "res_end",
        "req_id": req_id
    })
