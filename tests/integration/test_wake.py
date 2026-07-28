"""
Integration tests for the /wake endpoint.
"""

import time


class TestWakeEndpoint:
    """Tests for GET /wake."""

    def test_returns_200(self, client):
        resp = client.get("/wake")
        assert resp.status_code == 200

    def test_response_schema(self, client):
        data = client.get("/wake").get_json()
        assert set(data.keys()) == {"status", "timestamp"}

    def test_status_is_awake(self, client):
        data = client.get("/wake").get_json()
        assert data["status"] == "awake"

    def test_timestamp_is_recent(self, client):
        before = int(time.time())
        data = client.get("/wake").get_json()
        after = int(time.time())
        assert before <= data["timestamp"] <= after

    def test_timestamp_is_integer(self, client):
        data = client.get("/wake").get_json()
        assert isinstance(data["timestamp"], int)

    def test_post_not_allowed(self, client):
        resp = client.post("/wake")
        assert resp.status_code in (404, 405)
