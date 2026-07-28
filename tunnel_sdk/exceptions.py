"""
Custom exceptions for the Tunnel SDK.
"""

class TunnelError(Exception):
    """Base exception for all Tunnel SDK errors."""
    pass

class AuthenticationError(TunnelError):
    """Raised when the API key is invalid."""
    pass

class ConnectionError(TunnelError):
    """Raised when the WebSocket connection fails or drops unexpectedly."""
    pass

class ProtocolError(TunnelError):
    """Raised when the gateway sends malformed or incompatible protocol messages."""
    pass

class TimeoutError(TunnelError):
    """Raised when heartbeat or proxy requests time out."""
    pass
