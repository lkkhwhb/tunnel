"""
Configuration models for the Tunnel SDK.
"""
import os
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

@dataclass
class TunnelConfig:
    api_key: str
    target_path: str
    gateway: str = "wss://tunnel-g09n.onrender.com"
    local_url: Optional[str] = None
    port: int = 5000
    
    # Optional parameters
    max_reconnects: int = -1  # -1 for infinite
    reconnect_base_delay: float = 1.0
    reconnect_max_delay: float = 60.0
    ping_timeout: float = 45.0
    proxy_timeout: float = 30.0
    
    @classmethod
    def from_env(cls) -> "TunnelConfig":
        """Loads configuration from environment variables (including .env file)."""
        load_dotenv()  # Load variables from .env if present
        
        gateway = os.environ.get("TUNNEL_GATEWAY", "wss://tunnel-g09n.onrender.com")
        api_key = os.environ.get("TUNNEL_API_KEY")
        target_path = os.environ.get("TUNNEL_TARGET_PATH")
        
        port_str = os.environ.get("TUNNEL_PORT", "5000")
        port = int(port_str)
        
        local_url = os.environ.get("TUNNEL_LOCAL_URL")
        if not local_url:
            local_url = f"http://127.0.0.1:{port}"
        
        if not api_key:
            raise ValueError("TUNNEL_API_KEY environment variable is missing")
        if not target_path:
            raise ValueError("TUNNEL_TARGET_PATH environment variable is missing")
            
        return cls(
            api_key=api_key,
            target_path=target_path,
            gateway=gateway,
            local_url=local_url,
            port=port
        )
