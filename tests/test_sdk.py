import pytest
import os
import time
from unittest.mock import patch, MagicMock

from tunnel_sdk.client import Tunnel
from tunnel_sdk.config import TunnelConfig
from tunnel_sdk.protocol import encode_base64, decode_base64

def test_config_from_env(monkeypatch):
    monkeypatch.setenv("TUNNEL_GATEWAY", "wss://example.com")
    monkeypatch.setenv("TUNNEL_API_KEY", "secret")
    monkeypatch.setenv("TUNNEL_TARGET_PATH", "/api")
    
    config = TunnelConfig.from_env()
    assert config.gateway == "wss://example.com"
    assert config.api_key == "secret"
    assert config.target_path == "/api"

def test_protocol_encoding():
    original = b"hello world"
    encoded = encode_base64(original)
    assert isinstance(encoded, str)
    decoded = decode_base64(encoded)
    assert decoded == original

def test_tunnel_stats():
    tunnel = Tunnel(gateway="wss://test", api_key="key", target_path="/test")
    
    tunnel.stats.inc_active_requests()
    assert tunnel.stats.active_requests == 1
    
    tunnel.stats.dec_active_requests()
    assert tunnel.stats.active_requests == 0
    assert tunnel.stats.requests_handled == 1

def test_tunnel_events():
    tunnel = Tunnel(gateway="wss://test", api_key="key", target_path="/test")
    
    called = []
    def on_connect():
        called.append(True)
        
    tunnel.on("on_connect", on_connect)
    tunnel.events.emit("on_connect")
    
    assert len(called) == 1

@patch("tunnel_sdk.connection.websocket.WebSocketApp")
def test_graceful_shutdown(mock_ws):
    mock_app_instance = MagicMock()
    mock_ws.return_value = mock_app_instance
    
    tunnel = Tunnel(gateway="wss://test", api_key="key", target_path="/test")
    tunnel.start(local_url="http://localhost:5000")
    
    assert tunnel._is_running
    time.sleep(0.1) # Let thread start
    
    tunnel.stop()
    assert not tunnel._is_running
    mock_app_instance.close.assert_called_once()
    
def test_context_manager():
    with patch("tunnel_sdk.client.Tunnel.start") as mock_start:
        with patch("tunnel_sdk.client.Tunnel.stop") as mock_stop:
            with Tunnel(gateway="wss://test", api_key="key", target_path="/test", local_url="http://127.0.0.1:5000") as t:
                pass
            mock_start.assert_called_once()
            mock_stop.assert_called_once()
