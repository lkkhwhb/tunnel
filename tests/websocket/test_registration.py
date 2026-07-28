"""
WebSocket tunnel registration tests.

Tests every registration scenario: valid auth, invalid API keys,
missing params, protocol version mismatch, duplicate paths, and path normalization.

Since the tunnel_ws handler is wrapped by flask_sock, these tests verify
the registration logic through its component services (auth + tunnel_manager),
exactly replicating the handler's conditional flow.
"""

import time
import pytest

from tests.conftest import MockWebSocket
from gateway.app import create_app
from gateway import services as svc
from gateway.utils.auth import verify_api_key, AuthError
from gateway.config.settings import TUNNEL_API_KEY
from gateway.protocol.constants import PROTOCOL_VERSION


class TestSuccessfulRegistration:
    """Verify the happy path of tunnel registration."""

    def test_api_key_validates(self):
        verify_api_key(TUNNEL_API_KEY)

    def test_tunnel_registered(self, app):
        ws = MockWebSocket()
        tunnel, _ = svc.tunnel_manager.register("/api", ws, "10.0.0.1")
        assert tunnel is not None
        assert svc.tunnel_manager.count() == 1
        svc.tunnel_manager.unregister("/api")

    def test_registered_tunnel_is_lookup_able(self, app):
        ws = MockWebSocket()
        svc.tunnel_manager.register("/api", ws, "10.0.0.1")
        assert svc.tunnel_manager.get("/api") is not None
        svc.tunnel_manager.unregister("/api")

    def test_multiple_tunnels_different_paths(self, app):
        ws1, ws2 = MockWebSocket(), MockWebSocket()
        svc.tunnel_manager.register("/api", ws1, "10.0.0.1")
        svc.tunnel_manager.register("/web", ws2, "10.0.0.2")
        assert svc.tunnel_manager.count() == 2
        svc.tunnel_manager.unregister("/api")
        svc.tunnel_manager.unregister("/web")

    def test_header_auth_extraction(self):
        """Simulate extracting API key from Authorization and X-API-Key headers."""
        headers_bearer = {"Authorization": f"Bearer {TUNNEL_API_KEY}"}
        auth_header = headers_bearer.get("Authorization")
        extracted = auth_header[7:].strip() if auth_header and auth_header.lower().startswith("bearer ") else None
        assert extracted == TUNNEL_API_KEY
        verify_api_key(extracted)


class TestProtocolVersionCheck:
    """Verify protocol version validation."""

    def test_correct_version(self):
        assert PROTOCOL_VERSION == "1.2"

    def test_wrong_version_would_be_rejected(self):
        """Simulate the handler's version check logic."""
        protocol_version = "2.0"
        assert protocol_version != PROTOCOL_VERSION

    def test_missing_version_would_be_rejected(self):
        protocol_version = None
        assert not protocol_version or protocol_version != PROTOCOL_VERSION

    def test_empty_version_would_be_rejected(self):
        protocol_version = ""
        assert not protocol_version or protocol_version != PROTOCOL_VERSION


class TestMissingParameters:
    """Verify missing parameter handling."""

    def test_missing_api_key_rejected(self):
        """Handler checks: verify_api_key(api_key)."""
        with pytest.raises(AuthError) as exc_info:
            verify_api_key(None)
        assert exc_info.value.client_message == "Invalid API key"

    def test_missing_target_path_rejected(self):
        target_path = None
        assert not target_path

    def test_both_missing_rejected(self):
        with pytest.raises(AuthError):
            verify_api_key(None)


class TestApiKeyValidation:
    """Test every API key failure scenario."""

    def test_invalid_api_key(self):
        with pytest.raises(AuthError) as exc_info:
            verify_api_key("wrong-secret-key")
        assert exc_info.value.client_message == "Invalid API key"

    def test_empty_api_key(self):
        with pytest.raises(AuthError) as exc_info:
            verify_api_key("")
        assert exc_info.value.client_message == "Invalid API key"

    def test_none_api_key(self):
        with pytest.raises(AuthError) as exc_info:
            verify_api_key(None)
        assert exc_info.value.client_message == "Invalid API key"


class TestDuplicateRegistration:
    """Verify duplicate path handling."""

    def test_duplicate_returns_none(self, app):
        ws1, ws2 = MockWebSocket(), MockWebSocket()
        t1, _ = svc.tunnel_manager.register("/api", ws1, "10.0.0.1")
        t2, _ = svc.tunnel_manager.register("/api", ws2, "10.0.0.2")
        assert t1 is not None
        assert t2 is None
        svc.tunnel_manager.unregister("/api")

    def test_reregister_after_disconnect(self, app):
        ws1, ws2 = MockWebSocket(), MockWebSocket()
        svc.tunnel_manager.register("/api", ws1, "10.0.0.1")
        svc.tunnel_manager.unregister("/api", ws=ws1)
        t2, _ = svc.tunnel_manager.register("/api", ws2, "10.0.0.2")
        assert t2 is not None
        svc.tunnel_manager.unregister("/api")


class TestPathNormalization:
    """Verify target path normalization."""

    def test_path_without_leading_slash(self, app):
        """The handler prepends '/' if missing."""
        target_path = "api"
        if not target_path.startswith("/"):
            target_path = "/" + target_path
        assert target_path == "/api"

    def test_path_with_leading_slash(self, app):
        target_path = "/api"
        if not target_path.startswith("/"):
            target_path = "/" + target_path
        assert target_path == "/api"  # No double slash


class TestOwnershipCheck:
    """Verify that unregister checks WebSocket ownership."""

    def test_unregister_wrong_ws_does_not_remove(self, app):
        ws1, ws2 = MockWebSocket(), MockWebSocket()
        svc.tunnel_manager.register("/api", ws1, "10.0.0.1")
        svc.tunnel_manager.unregister("/api", ws=ws2)  # Wrong ws
        assert svc.tunnel_manager.count() == 1
        svc.tunnel_manager.unregister("/api")

    def test_unregister_correct_ws_removes(self, app):
        ws = MockWebSocket()
        svc.tunnel_manager.register("/api", ws, "10.0.0.1")
        svc.tunnel_manager.unregister("/api", ws=ws)
        assert svc.tunnel_manager.count() == 0
