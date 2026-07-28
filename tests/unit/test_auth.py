"""
Unit tests for gateway.utils.auth.

Tests API key verification: valid keys, wrong keys, empty keys, and missing keys.
"""

import pytest

from gateway.utils.auth import verify_api_key, AuthError
from gateway.config.settings import TUNNEL_API_KEY


class TestValidApiKey:
    """Tests for successful authentication."""

    def test_valid_key_succeeds(self):
        verify_api_key(TUNNEL_API_KEY)


class TestInvalidApiKey:
    """Tests for authentication failures."""

    def test_wrong_key_raises(self):
        with pytest.raises(AuthError) as exc_info:
            verify_api_key("wrong-secret-key")
        assert exc_info.value.client_message == "Invalid API key"

    def test_empty_key_raises(self):
        with pytest.raises(AuthError) as exc_info:
            verify_api_key("")
        assert exc_info.value.client_message == "Invalid API key"

    def test_none_key_raises(self):
        with pytest.raises(AuthError) as exc_info:
            verify_api_key(None)
        assert exc_info.value.client_message == "Invalid API key"

    def test_log_detail_present(self):
        with pytest.raises(AuthError) as exc_info:
            verify_api_key("invalid")
        assert "Invalid API key" in exc_info.value.log_detail


class TestDummyApiKeys:
    """Tests for dummy API key management and verification."""

    def test_add_and_verify_dummy_key(self):
        from gateway.utils.auth import add_dummy_api_key, remove_dummy_api_key, list_dummy_api_keys
        add_dummy_api_key("dummy_test_key_123")
        assert "dummy_test_key_123" in list_dummy_api_keys()
        verify_api_key("dummy_test_key_123")  # Should not raise
        remove_dummy_api_key("dummy_test_key_123")
        assert "dummy_test_key_123" not in list_dummy_api_keys()
        with pytest.raises(AuthError):
            verify_api_key("dummy_test_key_123")
