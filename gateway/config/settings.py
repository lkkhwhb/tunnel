"""
Application configuration loaded from environment variables.

All configuration values are centralized here to provide a single source
of truth for the entire application. Values are read from environment
variables with sensible defaults for local development.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH)

# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------
SERVER_VERSION = "1.2.0"
PROTOCOL_VERSION = "1.2"

# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 5000))

# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------
TUNNEL_TIMEOUT = float(os.getenv("TUNNEL_TIMEOUT", 30.0))
PING_INTERVAL = int(os.getenv("PING_INTERVAL", 15))
PING_TIMEOUT = int(os.getenv("PING_TIMEOUT", 45))

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
TUNNEL_API_KEY = os.getenv("TUNNEL_API_KEY")
if not TUNNEL_API_KEY:
    raise RuntimeError(
        "TUNNEL_API_KEY environment variable is required and must be set in gateway/config/.env"
    )

# ---------------------------------------------------------------------------
# Streaming / Chunked Transfer
# ---------------------------------------------------------------------------
# Requests larger than this threshold (or using chunked encoding) are
# forwarded using the streaming protocol instead of single-message mode.
STREAMING_THRESHOLD_BYTES = int(os.getenv("STREAMING_THRESHOLD_BYTES", 1024 * 1024))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 32 * 1024))

# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------
RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "500 per minute")
