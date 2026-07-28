"""
Gunicorn production configuration.

Optimized for Render.com deployment with WebSocket tunnel support.
Worker count auto-scales based on available CPU cores.
"""

import multiprocessing
import os

# --- Bind ---
bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"

# --- Workers ---
# gthread worker class supports WebSocket connections via threading.
# (2 × cores) + 1 is the Gunicorn-recommended formula.
workers = int(os.getenv("WEB_CONCURRENCY", (2 * multiprocessing.cpu_count()) + 1))
threads = int(os.getenv("GUNICORN_THREADS", 4))
worker_class = "gthread"

# --- Timeouts ---
# Long timeout for WebSocket upgrade handshakes and idle tunnels.
timeout = int(os.getenv("GUNICORN_TIMEOUT", 120))
graceful_timeout = 30
keepalive = 5

# --- Logging ---
# Disable Gunicorn's default access log (we use our own structured logger).
accesslog = None
errorlog = "-"  # stderr
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "warning")

# --- Security ---
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190

# --- Server Mechanics ---
preload_app = False  # Each worker gets its own app instance (important for threading)
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", 0))  # 0 = disabled
max_requests_jitter = 50  # Stagger restarts to avoid thundering herd

# --- Process Naming ---
proc_name = "tunnel-gateway"
