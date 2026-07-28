"""
Unit tests for gateway.protocol.constants and gateway.protocol.messages.

Verifies that all protocol constants have the expected string values
and that every message builder produces valid, correctly-structured JSON.
"""

import json

from gateway.protocol.constants import (
    SERVER_VERSION, PROTOCOL_VERSION,
    MSG_PING, MSG_PONG,
    MSG_REQ_SINGLE, MSG_REQ_START, MSG_REQ_CHUNK, MSG_REQ_END,
    MSG_RES_SINGLE, MSG_RES_START, MSG_RES_CHUNK, MSG_RES_END,
)
from gateway.protocol.messages import (
    build_ping, build_req_single, build_req_start,
    build_req_chunk, build_req_end,
)


class TestConstants:
    """Verify that all protocol constants match expected values."""

    def test_server_version(self):
        assert SERVER_VERSION == "1.2.0"

    def test_protocol_version(self):
        assert PROTOCOL_VERSION == "1.2"

    def test_heartbeat_types(self):
        assert MSG_PING == "ping"
        assert MSG_PONG == "pong"

    def test_request_types(self):
        assert MSG_REQ_SINGLE == "req_single"
        assert MSG_REQ_START == "req_start"
        assert MSG_REQ_CHUNK == "req_chunk"
        assert MSG_REQ_END == "req_end"

    def test_response_types(self):
        assert MSG_RES_SINGLE == "res_single"
        assert MSG_RES_START == "res_start"
        assert MSG_RES_CHUNK == "res_chunk"
        assert MSG_RES_END == "res_end"

    def test_all_types_are_strings(self):
        for const in (
            MSG_PING, MSG_PONG,
            MSG_REQ_SINGLE, MSG_REQ_START, MSG_REQ_CHUNK, MSG_REQ_END,
            MSG_RES_SINGLE, MSG_RES_START, MSG_RES_CHUNK, MSG_RES_END,
        ):
            assert isinstance(const, str)

    def test_all_types_unique(self):
        types = [
            MSG_PING, MSG_PONG,
            MSG_REQ_SINGLE, MSG_REQ_START, MSG_REQ_CHUNK, MSG_REQ_END,
            MSG_RES_SINGLE, MSG_RES_START, MSG_RES_CHUNK, MSG_RES_END,
        ]
        assert len(types) == len(set(types))


class TestBuildPing:
    """Tests for build_ping."""

    def test_valid_json(self):
        msg = json.loads(build_ping())
        assert msg == {"type": "ping"}

    def test_is_string(self):
        assert isinstance(build_ping(), str)


class TestBuildReqSingle:
    """Tests for build_req_single."""

    def test_contains_all_fields(self):
        msg = json.loads(build_req_single(
            "r1", "GET", "/users", "page=1",
            {"Accept": "application/json"}, b"body",
        ))
        assert msg["type"] == "req_single"
        assert msg["req_id"] == "r1"
        assert msg["method"] == "GET"
        assert msg["subpath"] == "/users"
        assert msg["query"] == "page=1"
        assert msg["headers"] == {"Accept": "application/json"}
        assert isinstance(msg["body"], str)  # base64 encoded

    def test_body_is_base64(self):
        from gateway.utils.encoding import b64_decode
        msg = json.loads(build_req_single(
            "r1", "POST", "/", "", {}, b"hello",
        ))
        assert b64_decode(msg["body"]) == b"hello"

    def test_empty_body(self):
        msg = json.loads(build_req_single("r1", "GET", "/", "", {}, b""))
        assert msg["body"] == ""

    def test_compressed_body(self):
        from gateway.utils.encoding import decode_payload
        large_body = b"A" * 200
        msg = json.loads(build_req_single("r1", "POST", "/", "", {}, large_body))
        assert msg.get("compressed") is True
        assert decode_payload(msg["body"], compressed=msg["compressed"]) == large_body


class TestBuildReqStart:
    """Tests for build_req_start."""

    def test_contains_all_fields(self):
        msg = json.loads(build_req_start(
            "r1", "PUT", "/upload", "", {"Content-Type": "text/plain"},
        ))
        assert msg["type"] == "req_start"
        assert msg["req_id"] == "r1"
        assert msg["method"] == "PUT"
        assert msg["subpath"] == "/upload"
        assert "headers" in msg

    def test_no_body_field(self):
        msg = json.loads(build_req_start("r1", "PUT", "/", "", {}))
        assert "body" not in msg


class TestBuildReqChunk:
    """Tests for build_req_chunk."""

    def test_contains_data(self):
        msg = json.loads(build_req_chunk("r1", b"chunk-data"))
        assert msg["type"] == "req_chunk"
        assert msg["req_id"] == "r1"
        assert isinstance(msg["data"], str)

    def test_data_decodes_correctly(self):
        from gateway.utils.encoding import b64_decode
        msg = json.loads(build_req_chunk("r1", b"binary\x00data"))
        assert b64_decode(msg["data"]) == b"binary\x00data"

    def test_compressed_chunk(self):
        from gateway.utils.encoding import decode_payload
        large_chunk = b"B" * 200
        msg = json.loads(build_req_chunk("r1", large_chunk))
        assert msg.get("compressed") is True
        assert decode_payload(msg["data"], compressed=msg["compressed"]) == large_chunk


class TestBuildReqEnd:
    """Tests for build_req_end."""

    def test_minimal_structure(self):
        msg = json.loads(build_req_end("r1"))
        assert msg == {"type": "req_end", "req_id": "r1"}

    def test_no_extra_fields(self):
        msg = json.loads(build_req_end("r1"))
        assert set(msg.keys()) == {"type", "req_id"}


class TestAllBuildersProduceValidJSON:
    """Ensure every builder returns parseable JSON."""

    def test_all_builders(self):
        builders = [
            lambda: build_ping(),
            lambda: build_req_single("r1", "GET", "/", "", {}, b""),
            lambda: build_req_start("r1", "GET", "/", "", {}),
            lambda: build_req_chunk("r1", b"data"),
            lambda: build_req_end("r1"),
        ]
        for builder in builders:
            result = builder()
            assert isinstance(result, str)
            parsed = json.loads(result)
            assert "type" in parsed
