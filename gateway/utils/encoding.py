"""
Base64 encoding / decoding utilities.

Wraps standard library functions for consistent usage across the codebase
and keeps the import surface small in calling modules.
"""

import base64


def b64_encode(data: bytes) -> str:
    """Encode raw bytes to a base64 UTF-8 string."""
    return base64.b64encode(data).decode("utf-8")


def b64_decode(data: str) -> bytes:
    """Decode a base64 string back to raw bytes."""
    return base64.b64decode(data)
