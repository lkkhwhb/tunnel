"""
WebSocket connection manager with reconnection logic.
"""
import json
import threading
import time
import urllib.parse
import websocket
import logging
from typing import Optional

from tunnel_sdk.config import TunnelConfig
from tunnel_sdk.events import EventEmitter
from tunnel_sdk.stats import TunnelStats
from tunnel_sdk.protocol import PROTOCOL_VERSION, build_pong, parse_message

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    RESET = '\033[0m'

logger = logging.getLogger("tunnel_sdk.connection")

class TunnelConnection:
    def __init__(self, config: TunnelConfig, stats: TunnelStats, events: EventEmitter):
        self.config = config
        self.stats = stats
        self.events = events
        self.ws_app: Optional[websocket.WebSocketApp] = None
        self.ws_thread: Optional[threading.Thread] = None
        
        self.dispatcher = None # Injected by client
        
        self._stop_event = threading.Event()
        self._reconnect_lock = threading.Lock()
        
        self.connected = False
        self.last_ping_time = 0.0

    def get_url(self) -> str:
        params = {
            "target_path": self.config.target_path,
            "protocol_version": PROTOCOL_VERSION
        }
        query = urllib.parse.urlencode(params)
        base = self.config.gateway
        if not base.endswith("/"):
            base += "/"
        return f"{base}ws/tunnel?{query}"

    def start(self):
        self._stop_event.clear()
        self._connect_loop()

    def _connect_loop(self):
        attempt = 0
        while not self._stop_event.is_set():
            url = self.get_url()
            
            if attempt == 0:
                self._wake_gateway()
                if self._stop_event.is_set():
                    break
                
            logger.info(f"Connecting to {self.config.gateway} as {self.config.target_path}")
            
            if attempt > 0:
                self.events.emit("on_reconnect_attempt", attempt)
                self.stats.inc_reconnect()
            
            headers = [
                f"Authorization: Bearer {self.config.api_key}",
                f"X-API-Key: {self.config.api_key}"
            ]
            self.ws_app = websocket.WebSocketApp(
                url,
                header=headers,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close
            )
            
            # This blocks until disconnected
            self.ws_app.run_forever()
            
            if self._stop_event.is_set():
                break
                
            self.connected = False
            
            if self.config.max_reconnects != -1 and attempt >= self.config.max_reconnects:
                self.events.emit("on_reconnect_failed")
                logger.error("Max reconnects reached. Stopping.")
                break
                
            # Backoff
            delay = min(self.config.reconnect_base_delay * (2 ** attempt), self.config.reconnect_max_delay)
            logger.info(f"Reconnecting in {delay} seconds...")
            attempt += 1
            time.sleep(delay)

    def _wake_gateway(self):
        """Sends a proactive HTTP request to wake up the gateway (e.g., if hosted on Render free tier)."""
        base_url = self.config.gateway.replace("wss://", "https://").replace("ws://", "http://").rstrip("/")
        if "localhost" in base_url or "127.0.0.1" in base_url or base_url == "https://test":
            return
        wake_url = f"{base_url}/wake"
        
        print("Checking if Gateway is awake (this may take 30-50s if Render is sleeping)...")
        try:
            import httpx
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(wake_url)
                if resp.status_code == 200:
                    print("Gateway is awake!")
        except Exception as e:
            logger.warning(f"Wake probe failed (will try websocket anyway): {e}")

    def stop(self):
        self._stop_event.set()
        if self.ws_app:
            self.ws_app.close()
            
    def send(self, data: str):
        if self.ws_app and self.connected:
            self.ws_app.send(data)

    def _on_open(self, ws):
        self.connected = True
        self.events.emit("on_connect")
        
        # Determine the public HTTP URL for user convenience
        base_url = self.config.gateway.replace("wss://", "https://").replace("ws://", "http://").rstrip("/")
        public_url = f"{base_url}{self.config.target_path}"
        local_url = self.config.local_url or "your local server"
        
        def print_success():
            time.sleep(0.5)
            if self.connected:
                print(f"\n{Colors.GREEN}" + "="*60)
                print("🚀 TUNNEL CONNECTED SUCCESSFULLY!")
                print(f"🌍 Public URL : {Colors.CYAN}{public_url}{Colors.GREEN}")
                print(f"🏠 Forwarding to : {Colors.CYAN}{local_url}{Colors.GREEN}")
                print("="*60 + f"{Colors.RESET}\n")
                logger.info(f"Tunnel connected successfully. Proxying {public_url} -> {local_url}")

        threading.Thread(target=print_success, daemon=True).start()

    def _on_message(self, ws, message):
        try:
            msg = parse_message(message)
        except Exception as e:
            logger.error(f"Error parsing message: {e}")
            return
            
        mtype = msg.get("type")
        
        # Check for immediate connection error frame
        if "error" in msg:
            error_msg = msg['error']
            logger.error(f"Gateway Error: {error_msg}")
            print(f"\n{Colors.RED}❌ TUNNEL ERROR: {error_msg}{Colors.RESET}\n")
            self.events.emit("on_error", Exception(error_msg))
            return

        if mtype == "ping":
            if self.last_ping_time > 0:
                latency = time.time() - self.last_ping_time
                self.stats.set_latency(latency)
            self.last_ping_time = time.time()
            self.send(build_pong())
        
        elif mtype == "req_single":
            if self.dispatcher:
                self.dispatcher.dispatch_single(msg)
                
        elif mtype == "req_start":
            if self.dispatcher:
                self.dispatcher.dispatch_start(msg)
                
        elif mtype == "req_chunk":
            if self.dispatcher:
                self.dispatcher.dispatch_chunk(msg)
                
        elif mtype == "req_end":
            if self.dispatcher:
                self.dispatcher.dispatch_end(msg)
        else:
            logger.warning(f"Unknown message type: {mtype}")

    def _on_error(self, ws, error):
        logger.error(f"WebSocket Error: {error}")
        self.events.emit("on_error", error)

    def _on_close(self, ws, close_status_code, close_msg):
        self.connected = False
        self.events.emit("on_disconnect")
        logger.info(f"Tunnel disconnected: {close_status_code} - {close_msg}")
