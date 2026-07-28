"""
Message builders for the WebSocket tunnel protocol.

Provides helper functions to construct well-formed protocol messages,
ensuring consistency and reducing error-prone manual dict construction.
"""

import json

from gateway.protocol.constants import (
    MSG_PING,
    MSG_REQ_SINGLE,
    MSG_REQ_START,
    MSG_REQ_CHUNK,
    MSG_REQ_END,
)
from gateway.utils.encoding import b64_encode, encode_payload


def build_ping() -> str:
    """Build a heartbeat ping message."""
    return json.dumps({"type": MSG_PING})


def build_req_single(
    req_id: str,
    method: str,
    subpath: str,
    query: str,
    headers: dict,
    body_bytes: bytes,
) -> str:
    """Build a single-message request payload.

    Used for requests whose body is smaller than the streaming threshold.
    The entire body is base64-encoded into a single JSON frame.
    """
    encoded_body, compressed = encode_payload(body_bytes, compress=True)
    payload = {
        "type": MSG_REQ_SINGLE,
        "req_id": req_id,
        "method": method,
        "subpath": subpath,
        "query": query,
        "headers": headers,
        "body": encoded_body,
    }
    if compressed:
        payload["compressed"] = True
    return json.dumps(payload)


def build_req_start(
    req_id: str,
    method: str,
    subpath: str,
    query: str,
    headers: dict,
) -> str:
    """Build the opening frame for a streaming request.

    Sent before any ``req_chunk`` frames.  Contains request metadata
    but no body data.
    """
    return json.dumps({
        "type": MSG_REQ_START,
        "req_id": req_id,
        "method": method,
        "subpath": subpath,
        "query": query,
        "headers": headers,
    })


def build_req_chunk(req_id: str, chunk_bytes: bytes) -> str:
    """Build a single chunk frame for a streaming request.

    Each chunk is base64-encoded independently.
    """
    encoded_data, compressed = encode_payload(chunk_bytes, compress=True)
    payload = {
        "type": MSG_REQ_CHUNK,
        "req_id": req_id,
        "data": encoded_data,
    }
    if compressed:
        payload["compressed"] = True
    return json.dumps(payload)


def build_req_end(req_id: str) -> str:
    """Build the sentinel frame that signals the end of a streaming request."""
    return json.dumps({
        "type": MSG_REQ_END,
        "req_id": req_id,
    })
