"""
Base64 encoding / decoding utilities.

Wraps standard library functions for consistent usage across the codebase
and keeps the import surface small in calling modules.
"""

import base64
import zlib


def b64_encode(data: bytes) -> str:
    """Encode raw bytes to a base64 UTF-8 string."""
    return base64.b64encode(data).decode("utf-8")


def b64_decode(data: str) -> bytes:
    """Decode a base64 string back to raw bytes."""
    return base64.b64decode(data)


def encode_payload(data: bytes, compress: bool = True) -> tuple[str, bool]:
    """Encode raw bytes to a base64 string, optionally compressing with zlib if beneficial.

    Returns:
        tuple[str, bool]: The encoded string and a boolean indicating whether compression was applied.
    """
    if not data:
        return "", False
    if compress and len(data) >= 64:
        try:
            compressed = zlib.compress(data)
            if len(compressed) < len(data):
                return b64_encode(compressed), True
        except Exception:
            pass
    return b64_encode(data), False


def decode_payload(data: str, compressed: bool = False) -> bytes:
    """Decode a base64 string back to raw bytes, decompressing if compressed."""
    if not data:
        return b""
    raw = b64_decode(data)
    if compressed:
        try:
            return zlib.decompress(raw)
        except Exception as e:
            raise ValueError(f"Failed to decompress payload: {e}") from e
    return raw
