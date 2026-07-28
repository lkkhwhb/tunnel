"""
Tunnel Gateway Python SDK
~~~~~~~~~~~~~~~~~~~~~~~~~

A production-quality Python SDK for the Tunnel Gateway.
"""

from tunnel_sdk.client import Tunnel
from tunnel_sdk.config import TunnelConfig
from tunnel_sdk.exceptions import (
    TunnelError, AuthenticationError, ConnectionError,
    ProtocolError, TimeoutError
)

__all__ = [
    "Tunnel",
    "TunnelConfig",
    "TunnelError",
    "AuthenticationError",
    "ConnectionError",
    "ProtocolError",
    "TimeoutError"
]
