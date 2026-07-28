"""
Unit tests for gateway.utils.encoding.

Verifies base64 encode/decode round-trips for text, binary, unicode,
empty, and large payloads.
"""

import pytest

from gateway.utils.encoding import b64_encode, b64_decode


class TestB64Encode:
    """Tests for b64_encode."""

    def test_simple_text(self):
        result = b64_encode(b"hello")
        assert isinstance(result, str)
        assert result == "aGVsbG8="

    def test_empty_bytes(self):
        assert b64_encode(b"") == ""

    def test_binary_data(self):
        data = bytes(range(256))
        encoded = b64_encode(data)
        assert isinstance(encoded, str)
        assert len(encoded) > 0

    def test_unicode_encoded_bytes(self):
        text = "こんにちは世界 🌍"
        data = text.encode("utf-8")
        encoded = b64_encode(data)
        assert isinstance(encoded, str)

    def test_large_payload(self):
        data = b"x" * (1024 * 1024)  # 1 MB
        encoded = b64_encode(data)
        assert len(encoded) > len(data)  # base64 expands size


class TestB64Decode:
    """Tests for b64_decode."""

    def test_simple_text(self):
        result = b64_decode("aGVsbG8=")
        assert result == b"hello"

    def test_empty_string(self):
        assert b64_decode("") == b""

    def test_invalid_base64(self):
        with pytest.raises(Exception):
            b64_decode("!!!not-valid-base64!!!")

    def test_binary_roundtrip(self):
        original = bytes(range(256))
        assert b64_decode(b64_encode(original)) == original


class TestRoundTrip:
    """Verify encode → decode produces the original data."""

    def test_text_roundtrip(self):
        original = b"The quick brown fox jumps over the lazy dog."
        assert b64_decode(b64_encode(original)) == original

    def test_unicode_roundtrip(self):
        text = "Ñoño señor café résumé naïve"
        original = text.encode("utf-8")
        assert b64_decode(b64_encode(original)) == original

    def test_null_bytes_roundtrip(self):
        original = b"\x00\x00\x00"
        assert b64_decode(b64_encode(original)) == original

    def test_all_byte_values_roundtrip(self):
        original = bytes(range(256)) * 10
        assert b64_decode(b64_encode(original)) == original

    def test_json_payload_roundtrip(self):
        import json
        payload = json.dumps({"key": "value", "number": 42}).encode()
        assert b64_decode(b64_encode(payload)) == payload


class TestPayloadEncoding:
    """Tests for encode_payload and decode_payload."""

    def test_small_payload_not_compressed(self):
        from gateway.utils.encoding import encode_payload, decode_payload
        data = b"small data"
        encoded, compressed = encode_payload(data, compress=True)
        assert not compressed
        assert decode_payload(encoded, compressed=compressed) == data

    def test_large_payload_compressed(self):
        from gateway.utils.encoding import encode_payload, decode_payload
        data = b"repetitive string " * 50
        encoded, compressed = encode_payload(data, compress=True)
        assert compressed
        assert len(encoded) < len(data)
        assert decode_payload(encoded, compressed=compressed) == data

    def test_empty_payload(self):
        from gateway.utils.encoding import encode_payload, decode_payload
        encoded, compressed = encode_payload(b"", compress=True)
        assert encoded == ""
        assert not compressed
        assert decode_payload("", compressed=False) == b""
