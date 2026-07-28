"""
Configuration models for the Tunnel SDK.
"""
import os
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class TunnelConfig:
    gateway: str
    api_key: str
    target_path: str
    local_url: Optional[str] = None
    
    # Optional parameters
    max_reconnects: int = -1  # -1 for infinite
    reconnect_base_delay: float = 1.0
    reconnect_max_delay: float = 60.0
    ping_timeout: float = 45.0
    proxy_timeout: float = 30.0
    
    @classmethod
    def from_env(cls) -> "TunnelConfig":
        """Loads configuration from environment variables."""
        gateway = os.environ.get("TUNNEL_GATEWAY")
        api_key = os.environ.get("TUNNEL_API_KEY")
        target_path = os.environ.get("TUNNEL_TARGET_PATH")
        local_url = os.environ.get("TUNNEL_LOCAL_URL")
        
        if not gateway:
            raise ValueError("TUNNEL_GATEWAY environment variable is missing")
        if not api_key:
            raise ValueError("TUNNEL_API_KEY environment variable is missing")
        if not target_path:
            raise ValueError("TUNNEL_TARGET_PATH environment variable is missing")
            
        return cls(
            gateway=gateway,
            api_key=api_key,
            target_path=target_path,
            local_url=local_url
        )
