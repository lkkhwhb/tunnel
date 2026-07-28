"""
Protocol utilities for encoding, decoding, and parsing Tunnel Gateway messages.
"""
import base64
import json
import zlib
from typing import Dict, Any, Optional, Tuple

from tunnel_sdk.exceptions import ProtocolError

from gateway.config.settings import PROTOCOL_VERSION

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

def encode_payload(data: bytes, compress: bool = True) -> Tuple[str, bool]:
    """Encode raw bytes to a base64 string, optionally compressing with zlib if beneficial."""
    if not data:
        return "", False
    if compress and len(data) >= 64:
        try:
            compressed = zlib.compress(data)
            if len(compressed) < len(data):
                return encode_base64(compressed), True
        except Exception:
            pass
    return encode_base64(data), False

def decode_payload(data: str, compressed: bool = False) -> bytes:
    """Decode a base64 string back to raw bytes, decompressing if compressed."""
    if not data:
        return b""
    raw = decode_base64(data)
    if compressed:
        try:
            return zlib.decompress(raw)
        except Exception as e:
            raise ProtocolError(f"Failed to decompress payload: {e}") from e
    return raw

def parse_message(raw_msg: str) -> Dict[str, Any]:
    """Parses a raw WebSocket message string into a JSON dictionary."""
    try:
        return json.loads(raw_msg)
    except json.JSONDecodeError as e:
        raise ProtocolError(f"Invalid JSON in message: {e}")

def build_pong() -> str:
    return json.dumps({"type": "pong"})

def build_res_single(req_id: str, status: int, headers: Dict[str, str], body: bytes) -> str:
    encoded_body, compressed = encode_payload(body, compress=True)
    payload = {
        "type": "res_single",
        "req_id": req_id,
        "status": status,
        "headers": headers,
        "body": encoded_body
    }
    if compressed:
        payload["compressed"] = True
    return json.dumps(payload)

def build_res_start(req_id: str, status: int, headers: Dict[str, str]) -> str:
    return json.dumps({
        "type": "res_start",
        "req_id": req_id,
        "status": status,
        "headers": headers
    })

def build_res_chunk(req_id: str, chunk: bytes) -> str:
    encoded_data, compressed = encode_payload(chunk, compress=True)
    payload = {
        "type": "res_chunk",
        "req_id": req_id,
        "data": encoded_data
    }
    if compressed:
        payload["compressed"] = True
    return json.dumps(payload)

def build_res_end(req_id: str) -> str:
    return json.dumps({
        "type": "res_end",
        "req_id": req_id
    })
