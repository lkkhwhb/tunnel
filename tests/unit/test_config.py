"""
Unit tests for gateway.config.settings.

Verifies that all configuration values are present, have correct types,
and use sensible defaults.
"""

from gateway.config.settings import (
    HOST, PORT, TUNNEL_TIMEOUT, PING_INTERVAL, PING_TIMEOUT,
    TUNNEL_API_KEY, STREAMING_THRESHOLD_BYTES, CHUNK_SIZE, RATE_LIMIT_DEFAULT,
)


class TestDefaultValues:
    """Verify every config value has a sensible default."""

    def test_host_is_string(self):
        assert isinstance(HOST, str)
        assert HOST == "0.0.0.0"

    def test_port_is_int(self):
        assert isinstance(PORT, int)
        assert PORT == 5000

    def test_tunnel_timeout_is_float(self):
        assert isinstance(TUNNEL_TIMEOUT, float)
        assert TUNNEL_TIMEOUT == 30.0

    def test_ping_interval_is_int(self):
        assert isinstance(PING_INTERVAL, int)
        assert PING_INTERVAL == 15

    def test_ping_timeout_is_int(self):
        assert isinstance(PING_TIMEOUT, int)
        assert PING_TIMEOUT == 45

    def test_tunnel_api_key_is_string(self):
        assert isinstance(TUNNEL_API_KEY, str)
        assert len(TUNNEL_API_KEY) > 0

    def test_streaming_threshold_is_int(self):
        assert isinstance(STREAMING_THRESHOLD_BYTES, int)
        assert STREAMING_THRESHOLD_BYTES == 1024 * 1024

    def test_chunk_size_is_int(self):
        assert isinstance(CHUNK_SIZE, int)
        assert CHUNK_SIZE == 32 * 1024

    def test_rate_limit_default_is_string(self):
        assert isinstance(RATE_LIMIT_DEFAULT, str)
        assert "per" in RATE_LIMIT_DEFAULT


class TestConfigConstraints:
    """Verify logical relationships between configuration values."""

    def test_ping_timeout_exceeds_interval(self):
        """Timeout should be longer than the ping interval."""
        assert PING_TIMEOUT > PING_INTERVAL

    def test_chunk_size_smaller_than_threshold(self):
        """Chunk size should be smaller than the streaming threshold."""
        assert CHUNK_SIZE < STREAMING_THRESHOLD_BYTES

    def test_all_timeouts_positive(self):
        assert TUNNEL_TIMEOUT > 0
        assert PING_INTERVAL > 0
        assert PING_TIMEOUT > 0

    def test_port_in_valid_range(self):
        assert 1 <= PORT <= 65535


class TestEnvVarOverride:
    """Verify that config reads from environment variables."""

    def test_config_uses_os_getenv(self, monkeypatch):
        """Reloading with env vars set produces different values."""
        import importlib
        from gateway.config import settings

        monkeypatch.setenv("PORT", "9999")
        monkeypatch.setenv("TUNNEL_TIMEOUT", "60.0")
        importlib.reload(settings)

        try:
            assert settings.PORT == 9999
            assert settings.TUNNEL_TIMEOUT == 60.0
        finally:
            monkeypatch.delenv("PORT", raising=False)
            monkeypatch.delenv("TUNNEL_TIMEOUT", raising=False)
            importlib.reload(settings)

    def test_missing_api_key_raises_runtime_error(self, monkeypatch):
        import importlib
        import pytest
        from gateway.config import settings

        monkeypatch.delenv("TUNNEL_API_KEY", raising=False)
        monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: None)
        try:
            with pytest.raises(RuntimeError, match="TUNNEL_API_KEY environment variable is required"):
                importlib.reload(settings)
        finally:
            monkeypatch.setenv("TUNNEL_API_KEY", "test-api-key-12345")
            importlib.reload(settings)
