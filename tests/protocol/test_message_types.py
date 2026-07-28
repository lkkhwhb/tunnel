"""
Protocol message type tests.

Comprehensive verification that all 10 protocol message types are correctly
defined and that builder functions produce structurally correct frames.
"""

import json

from gateway.protocol.constants import (
    MSG_PING, MSG_PONG,
    MSG_REQ_SINGLE, MSG_REQ_START, MSG_REQ_CHUNK, MSG_REQ_END,
    MSG_RES_SINGLE, MSG_RES_START, MSG_RES_CHUNK, MSG_RES_END,
)
from gateway.protocol.messages import (
    build_ping, build_req_single, build_req_start,
    build_req_chunk, build_req_end,
)
from gateway.utils.encoding import b64_encode, b64_decode


class TestAllMessageTypes:
    """Verify all 10 protocol message type constants."""

    def test_heartbeat_messages(self):
        assert MSG_PING == "ping"
        assert MSG_PONG == "pong"

    def test_single_request_messages(self):
        assert MSG_REQ_SINGLE == "req_single"
        assert MSG_RES_SINGLE == "res_single"

    def test_streaming_request_messages(self):
        assert MSG_REQ_START == "req_start"
        assert MSG_REQ_CHUNK == "req_chunk"
        assert MSG_REQ_END == "req_end"

    def test_streaming_response_messages(self):
        assert MSG_RES_START == "res_start"
        assert MSG_RES_CHUNK == "res_chunk"
        assert MSG_RES_END == "res_end"


class TestPingFrame:
    """Verify ping frame structure."""

    def test_structure(self):
        frame = json.loads(build_ping())
        assert frame == {"type": "ping"}

    def test_no_extra_fields(self):
        frame = json.loads(build_ping())
        assert len(frame) == 1


class TestReqSingleFrame:
    """Verify req_single frame structure."""

    def test_all_required_fields(self):
        frame = json.loads(build_req_single(
            "id-1", "POST", "/users", "sort=name",
            {"Accept": "text/html"}, b"payload",
        ))
        assert frame["type"] == "req_single"
        assert frame["req_id"] == "id-1"
        assert frame["method"] == "POST"
        assert frame["subpath"] == "/users"
        assert frame["query"] == "sort=name"
        assert frame["headers"] == {"Accept": "text/html"}
        assert b64_decode(frame["body"]) == b"payload"

    def test_exactly_seven_fields(self):
        frame = json.loads(build_req_single(
            "id-1", "GET", "/", "", {}, b"",
        ))
        assert len(frame) == 7


class TestReqStartFrame:
    """Verify req_start frame structure."""

    def test_all_required_fields(self):
        frame = json.loads(build_req_start(
            "id-1", "PUT", "/upload", "overwrite=true",
            {"Content-Type": "application/octet-stream"},
        ))
        assert frame["type"] == "req_start"
        assert frame["req_id"] == "id-1"
        assert frame["method"] == "PUT"
        assert frame["subpath"] == "/upload"
        assert frame["query"] == "overwrite=true"
        assert frame["headers"]["Content-Type"] == "application/octet-stream"

    def test_no_body_field(self):
        frame = json.loads(build_req_start("id-1", "PUT", "/", "", {}))
        assert "body" not in frame

    def test_exactly_six_fields(self):
        frame = json.loads(build_req_start("id-1", "PUT", "/", "", {}))
        assert len(frame) == 6


class TestReqChunkFrame:
    """Verify req_chunk frame structure."""

    def test_structure(self):
        frame = json.loads(build_req_chunk("id-1", b"binary-data"))
        assert frame["type"] == "req_chunk"
        assert frame["req_id"] == "id-1"
        assert b64_decode(frame["data"]) == b"binary-data"

    def test_exactly_three_fields(self):
        frame = json.loads(build_req_chunk("id-1", b"data"))
        assert len(frame) == 3


class TestReqEndFrame:
    """Verify req_end frame structure."""

    def test_structure(self):
        frame = json.loads(build_req_end("id-1"))
        assert frame == {"type": "req_end", "req_id": "id-1"}

    def test_exactly_two_fields(self):
        frame = json.loads(build_req_end("id-1"))
        assert len(frame) == 2


class TestResponseFrameContracts:
    """Verify the expected structure of response frames (built by SDKs)."""

    def test_res_single_expected_fields(self):
        """Verify what a well-formed res_single from an SDK should look like."""
        frame = {
            "type": MSG_RES_SINGLE,
            "req_id": "id-1",
            "status": 200,
            "headers": {"Content-Type": "text/plain"},
            "body": b64_encode(b"response body"),
        }
        assert frame["type"] == "res_single"
        assert isinstance(frame["status"], int)
        assert isinstance(frame["headers"], dict)
        assert b64_decode(frame["body"]) == b"response body"

    def test_res_start_expected_fields(self):
        frame = {
            "type": MSG_RES_START,
            "req_id": "id-1",
            "status": 200,
            "headers": {"Content-Type": "application/octet-stream"},
        }
        assert "body" not in frame
        assert frame["type"] == "res_start"

    def test_res_chunk_expected_fields(self):
        frame = {
            "type": MSG_RES_CHUNK,
            "req_id": "id-1",
            "data": b64_encode(b"chunk"),
        }
        assert b64_decode(frame["data"]) == b"chunk"

    def test_res_end_expected_fields(self):
        frame = {
            "type": MSG_RES_END,
            "req_id": "id-1",
        }
        assert len(frame) == 2
