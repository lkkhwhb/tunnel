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
            "api_key": self.config.api_key,
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
            logger.info(f"Connecting to {self.config.gateway} as {self.config.target_path}")
            
            if attempt > 0:
                self.events.emit("on_reconnect_attempt", attempt)
                self.stats.inc_reconnect()
            
            self.ws_app = websocket.WebSocketApp(
                url,
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
        logger.info("Tunnel connected successfully.")

    def _on_message(self, ws, message):
        try:
            msg = parse_message(message)
        except Exception as e:
            logger.error(f"Error parsing message: {e}")
            return
            
        mtype = msg.get("type")
        
        # Check for immediate connection error frame
        if "error" in msg:
            logger.error(f"Gateway Error: {msg['error']}")
            self.events.emit("on_error", Exception(msg["error"]))
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
