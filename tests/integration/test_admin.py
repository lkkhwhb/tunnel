"""
Integration tests for admin endpoints.

Validates response schemas, status codes, and expected field values
for /admin/status, /admin/health, and /admin/info.
"""

from tests.conftest import MockWebSocket
from gateway import services as svc
from gateway.config.settings import TUNNEL_API_KEY


class TestAdminStatus:
    """Tests for GET /admin/status."""

    def test_returns_200(self, client):
        resp = client.get("/admin/status")
        assert resp.status_code == 200

    def test_response_schema(self, client):
        data = client.get("/admin/status").get_json()
        assert data["status"] == "online"
        assert "uptime_seconds" in data
        assert "started_at" in data
        assert "total_requests" in data
        assert "active_requests" in data
        assert "average_latency_ms" in data
        assert "bytes_uploaded" in data
        assert "bytes_downloaded" in data
        assert "total_bytes_transferred" in data
        assert "active_tunnels_count" in data
        assert "tunnels" in data

    def test_unauth_hides_tunnels(self, client, registered_tunnel):
        data = client.get("/admin/status").get_json()
        assert data["active_tunnels_count"] == "Hidden (Auth Required)"
        assert data["tunnels"] == []

    def test_no_tunnels_initially(self, client):
        data = client.get("/admin/status", headers={"X-API-Key": TUNNEL_API_KEY}).get_json()
        assert data["active_tunnels_count"] == 0
        assert data["tunnels"] == []

    def test_with_active_tunnel(self, client, registered_tunnel):
        data = client.get("/admin/status", headers={"X-API-Key": TUNNEL_API_KEY}).get_json()
        assert data["active_tunnels_count"] == 1
        assert len(data["tunnels"]) == 1
        tunnel_info = data["tunnels"][0]
        assert tunnel_info["target_path"] == "/test"
        assert "client_ip" in tunnel_info
        assert "uptime_seconds" in tunnel_info
        assert "requests_served" in tunnel_info
        assert "bytes_uploaded" in tunnel_info
        assert "bytes_downloaded" in tunnel_info
        assert "total_bytes_transferred" in tunnel_info

    def test_uptime_positive(self, client):
        data = client.get("/admin/status").get_json()
        assert data["uptime_seconds"] >= 0

    def test_started_at_is_timestamp(self, client):
        data = client.get("/admin/status").get_json()
        assert isinstance(data["started_at"], float)
        assert data["started_at"] > 0


class TestAdminHealth:
    """Tests for GET /admin/health."""

    def test_returns_200(self, client):
        resp = client.get("/admin/health")
        assert resp.status_code == 200

    def test_response_schema(self, client):
        data = client.get("/admin/health").get_json()
        expected_keys = {
            "cpu_usage_percent", "memory_usage_percent",
            "used_memory_bytes", "total_memory_bytes",
            "thread_count", "process_id", "python_thread_count",
            "active_tunnels", "active_requests", "total_requests",
            "bytes_uploaded", "bytes_downloaded", "average_latency_ms",
            "server_uptime_seconds", "websocket_tunnel_count",
        }
        assert set(data.keys()) == expected_keys

    def test_process_id_is_positive(self, client):
        data = client.get("/admin/health").get_json()
        assert data["process_id"] > 0

    def test_memory_values_positive(self, client):
        data = client.get("/admin/health").get_json()
        assert data["total_memory_bytes"] > 0
        assert data["used_memory_bytes"] > 0

    def test_thread_count_positive(self, client):
        data = client.get("/admin/health").get_json()
        assert data["thread_count"] >= 1
        assert data["python_thread_count"] >= 1

    def test_tunnel_counts_match(self, client, registered_tunnel):
        data = client.get("/admin/health", headers={"X-API-Key": TUNNEL_API_KEY}).get_json()
        assert data["active_tunnels"] == 1
        assert data["websocket_tunnel_count"] == 1

    def test_unauth_health_hides_tunnels(self, client, registered_tunnel):
        data = client.get("/admin/health").get_json()
        assert data["active_tunnels"] == "Hidden"
        assert data["websocket_tunnel_count"] == "Hidden"


class TestAdminInfo:
    """Tests for GET /admin/info."""

    def test_returns_200(self, client):
        resp = client.get("/admin/info")
        assert resp.status_code == 200

    def test_response_schema(self, client):
        data = client.get("/admin/info").get_json()
        expected_keys = {
            "server_version", "protocol_version", "python_version",
            "operating_system", "hostname", "startup_time",
            "streaming_support", "binary_frame_support",
            "compression_support",
        }
        assert set(data.keys()) == expected_keys

    def test_versions(self, client):
        data = client.get("/admin/info").get_json()
        assert data["server_version"] == "1.2.0"
        assert data["protocol_version"] == "1.2"

    def test_capability_flags(self, client):
        data = client.get("/admin/info").get_json()
        assert data["streaming_support"] is True
        assert data["binary_frame_support"] is False
        assert data["compression_support"] is False

    def test_hostname_is_string(self, client):
        data = client.get("/admin/info").get_json()
        assert isinstance(data["hostname"], str)
        assert len(data["hostname"]) > 0

    def test_startup_time_is_timestamp(self, client):
        data = client.get("/admin/info").get_json()
        assert isinstance(data["startup_time"], float)
        assert data["startup_time"] > 0
