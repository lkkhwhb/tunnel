"""
Thread-safe statistics tracking.
"""
import threading
import time

class TunnelStats:
    def __init__(self):
        self._lock = threading.Lock()
        self.requests_handled = 0
        self.active_requests = 0
        self.bytes_uploaded = 0
        self.bytes_downloaded = 0
        self.reconnect_count = 0
        self.start_time = time.time()
        self.last_heartbeat_latency = 0.0
        
    @property
    def uptime(self) -> float:
        return time.time() - self.start_time

    def inc_active_requests(self):
        with self._lock:
            self.active_requests += 1

    def dec_active_requests(self):
        with self._lock:
            self.active_requests = max(0, self.active_requests - 1)
            self.requests_handled += 1

    def add_bytes_uploaded(self, count: int):
        with self._lock:
            self.bytes_uploaded += count
            
    def add_bytes_downloaded(self, count: int):
        with self._lock:
            self.bytes_downloaded += count
            
    def inc_reconnect(self):
        with self._lock:
            self.reconnect_count += 1
            
    def set_latency(self, latency: float):
        with self._lock:
            self.last_heartbeat_latency = latency
