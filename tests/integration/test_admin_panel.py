"""
Integration tests for the Gateway Admin Panel and Dashboard.

Tests serving the UI at root (/), static assets, API key authentication,
runtime configuration modification, and tunnel management.
"""

from gateway.config.settings import TUNNEL_API_KEY
from gateway import services as svc


class TestDashboardUI:
    """Tests for web route UI serving."""

    def test_serve_dashboard_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Tunnel Gateway" in resp.get_data(as_text=True)

    def test_serve_dashboard_admin(self, client):
        resp = client.get("/admin")
        assert resp.status_code == 200
        assert "Tunnel Gateway" in resp.get_data(as_text=True)

    def test_serve_dashboard_index(self, client):
        resp = client.get("/index.html")
        assert resp.status_code == 200
        assert "Tunnel Gateway" in resp.get_data(as_text=True)

    def test_serve_static_css(self, client):
        resp = client.get("/static/css/style.css")
        assert resp.status_code == 200
        assert "color-tokens" in resp.get_data(as_text=True).lower() or "--bg-main" in resp.get_data(as_text=True)

    def test_serve_static_js(self, client):
        resp = client.get("/static/js/app.js")
        assert resp.status_code == 200
        assert "tunnel_api_key" in resp.get_data(as_text=True)


class TestApiKeyAuth:
    """Tests for API key verification endpoint."""

    def test_verify_unauthorized(self, client):
        resp = client.post("/admin/verify", json={"api_key": "wrong_key"})
        assert resp.status_code == 401
        assert "error" in resp.get_json()

    def test_verify_success_header(self, client):
        resp = client.post("/admin/verify", headers={"X-API-Key": TUNNEL_API_KEY})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "valid"

    def test_verify_success_bearer(self, client):
        resp = client.post("/admin/verify", headers={"Authorization": f"Bearer {TUNNEL_API_KEY}"})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "valid"


class TestAdminSettings:
    """Tests for runtime configuration settings management."""

    def test_get_settings_unauth(self, client):
        resp = client.get("/admin/settings")
        assert resp.status_code == 401

    def test_get_settings_success(self, client):
        resp = client.get("/admin/settings", headers={"X-API-Key": TUNNEL_API_KEY})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "streaming_threshold_bytes" in data
        assert "chunk_size" in data
        assert "tunnel_timeout" in data

    def test_update_settings_success(self, client):
        headers = {"X-API-Key": TUNNEL_API_KEY}
        payload = {
            "streaming_threshold_bytes": 2048000,
            "tunnel_timeout": 60.0
        }
        resp = client.post("/admin/settings", json=payload, headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "updated"
        assert data["settings"]["streaming_threshold_bytes"] == 2048000
        assert data["settings"]["tunnel_timeout"] == 60.0


class TestAdminTunnelManagement:
    """Tests for active tunnel management and stat resets."""

    def test_delete_tunnel_not_found(self, client):
        resp = client.delete("/admin/tunnels?path=/nonexistent", headers={"X-API-Key": TUNNEL_API_KEY})
        assert resp.status_code == 404

    def test_delete_tunnel_success(self, client, registered_tunnel):
        assert svc.tunnel_manager.count() == 1
        resp = client.delete("/admin/tunnels?path=/test", headers={"X-API-Key": TUNNEL_API_KEY})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "disconnected"
        assert svc.tunnel_manager.count() == 0

    def test_reset_stats_success(self, client):
        svc.server_stats.record_request_start()
        svc.server_stats.record_upload(500)
        assert svc.server_stats.total_requests == 1

        resp = client.post("/admin/stats/reset", headers={"X-API-Key": TUNNEL_API_KEY})
        assert resp.status_code == 200
        assert svc.server_stats.total_requests == 0
        assert svc.server_stats.bytes_uploaded == 0


class TestDummyKeysManagement:
    """Tests for dummy/temporary API key management endpoints."""

    def test_keys_unauth(self, client):
        resp = client.get("/admin/keys")
        assert resp.status_code == 401

    def test_create_list_delete_dummy_key(self, client):
        headers = {"X-API-Key": TUNNEL_API_KEY}

        # Create a custom dummy key
        resp = client.post("/admin/keys", json={"key": "friend_key_99"}, headers=headers)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["key"] == "friend_key_99"
        assert "friend_key_99" in data["dummy_keys"]

        # Verify friend can authenticate using this key
        auth_resp = client.post("/admin/verify", headers={"X-API-Key": "friend_key_99"})
        assert auth_resp.status_code == 200

        # List keys
        list_resp = client.get("/admin/keys", headers=headers)
        assert list_resp.status_code == 200
        assert "friend_key_99" in list_resp.get_json()["dummy_keys"]

        # Delete key
        del_resp = client.delete("/admin/keys?key=friend_key_99", headers=headers)
        assert del_resp.status_code == 200
        assert "friend_key_99" not in del_resp.get_json()["dummy_keys"]

        # Verify friend can no longer authenticate
        auth_resp2 = client.post("/admin/verify", headers={"X-API-Key": "friend_key_99"})
        assert auth_resp2.status_code == 401
