"""
The main Tunnel client class for the SDK.
"""
import threading
import time
import logging
import os
from typing import Optional, Callable

from tunnel_sdk.config import TunnelConfig
from tunnel_sdk.stats import TunnelStats
from tunnel_sdk.events import EventEmitter
from tunnel_sdk.connection import TunnelConnection
from tunnel_sdk.dispatcher import RequestDispatcher
from tunnel_sdk.protocol import PROTOCOL_VERSION

__version__ = "1.0.0"

logger = logging.getLogger("tunnel_sdk")

class Tunnel:
    def __init__(self, api_key: str = None, target_path: str = None, gateway: str = None, port: int = None, local_url: str = None, **kwargs):
        # Support default from env if not provided
        if gateway is None: gateway = os.environ.get("TUNNEL_GATEWAY", "wss://tunnel-g09n.onrender.com")
        if api_key is None: api_key = os.environ.get("TUNNEL_API_KEY")
        if target_path is None: target_path = os.environ.get("TUNNEL_TARGET_PATH")
        
        if port is None: port = int(os.environ.get("TUNNEL_PORT", 5000))
        if local_url is None: local_url = os.environ.get("TUNNEL_LOCAL_URL")
        
        if not local_url:
            local_url = f"http://127.0.0.1:{port}"
        
        if not api_key or not target_path:
            raise ValueError("api_key and target_path must be provided or set in environment variables")
            
        self.config = TunnelConfig(
            api_key=api_key,
            target_path=target_path,
            gateway=gateway,
            local_url=local_url,
            port=port,
            **kwargs
        )
        self.stats = TunnelStats()
        self.events = EventEmitter()
        
        self._connection = TunnelConnection(self.config, self.stats, self.events)
        self._dispatcher: Optional[RequestDispatcher] = None
        self._main_thread: Optional[threading.Thread] = None
        
        # To handle graceful shutdown
        self._is_running = False

    @classmethod
    def from_env(cls, **kwargs) -> "Tunnel":
        config = TunnelConfig.from_env()
        return cls(
            api_key=config.api_key,
            target_path=config.target_path,
            gateway=config.gateway,
            local_url=config.local_url,
            port=config.port,
            **kwargs
        )

    def on(self, event: str, callback: Callable) -> None:
        """Register an event callback."""
        self.events.on(event, callback)

    def off(self, event: str, callback: Callable) -> None:
        """Unregister an event callback."""
        self.events.off(event, callback)

    def start(self, port: Optional[int] = None, local_url: Optional[str] = None) -> None:
        """Starts the tunnel in a background thread."""
        if self._is_running:
            return
            
        url_to_use = local_url or self.config.local_url
        if port is not None:
            url_to_use = f"http://127.0.0.1:{port}"
            
        if not url_to_use:
            raise ValueError("local_url or port must be provided either in Tunnel() or start()")
            
        self._is_running = True
        self._dispatcher = RequestDispatcher(
            local_url=url_to_use,
            ws_send_func=self._connection.send,
            stats=self.stats,
            events=self.events
        )
        self._connection.dispatcher = self._dispatcher
        
        self._main_thread = threading.Thread(target=self._connection.start, daemon=True)
        self._main_thread.start()
        logger.info("Tunnel background thread started.")

    def run(self, port: Optional[int] = None, local_url: Optional[str] = None) -> None:
        """Starts the tunnel and blocks the current thread until stopped."""
        self.start(port=port, local_url=local_url)
        self.wait()

    def stop(self) -> None:
        """Stops the tunnel and performs graceful shutdown."""
        if not self._is_running:
            return
            
        self._is_running = False
        logger.info("Stopping tunnel...")
        
        self._connection.stop()
        if self._dispatcher:
            self._dispatcher.shutdown()
            
        if self._main_thread and self._main_thread.is_alive():
            self._main_thread.join(timeout=5.0)

    def restart(self, port: Optional[int] = None, local_url: Optional[str] = None) -> None:
        """Restarts the tunnel connection."""
        self.stop()
        # Wait a moment for resources to clean up
        time.sleep(1)
        self.start(port=port, local_url=local_url)

    def wait(self) -> None:
        """Blocks until the tunnel is stopped."""
        try:
            while self._is_running and self._main_thread and self._main_thread.is_alive():
                time.sleep(1.0)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received.")
            self.stop()

    def __enter__(self):
        self.start()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
    
    # Properties
    @property
    def is_connected(self) -> bool:
        return self._connection.connected

    @property
    def gateway_version(self) -> Optional[str]:
        # Would be fetched via admin info or headers, but not required right now
        return None

    @property
    def protocol_version(self) -> str:
        return PROTOCOL_VERSION

    @property
    def sdk_version(self) -> str:
        return __version__

    @property
    def last_error(self) -> Optional[Exception]:
        return None # Could store the last error caught in connection.py

    @property
    def reconnect_count(self) -> int:
        return self.stats.reconnect_count

    @property
    def uptime(self) -> float:
        return self.stats.uptime

    @property
    def statistics(self) -> dict:
        return {
            "requests_handled": self.stats.requests_handled,
            "active_requests": self.stats.active_requests,
            "bytes_uploaded": self.stats.bytes_uploaded,
            "bytes_downloaded": self.stats.bytes_downloaded,
            "reconnect_count": self.stats.reconnect_count,
            "uptime": self.stats.uptime,
            "last_heartbeat_latency": self.stats.last_heartbeat_latency,
        }
