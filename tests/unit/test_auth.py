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
