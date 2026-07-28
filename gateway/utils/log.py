"""
Production logging configuration.

Provides structured JSON logging with automatic sensitive-data redaction
and configurable request sampling to keep log volume manageable at scale.

All modules should use ``get_logger(__name__)`` to obtain their logger.
"""

import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone

_configured = False
_log_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Request Sampling
# ---------------------------------------------------------------------------

_sample_counter = 0
_sample_lock = threading.Lock()


def should_sample(rate: int) -> bool:
    """
    Return ``True`` for every *rate*-th call.  Thread-safe.

    Used to log only a fraction of high-volume events (e.g. per-request
    completion logs).  A rate of 1 logs everything; 100 logs ~1%.

    Args:
        rate: Log one out of every *rate* events.
    """
    if rate <= 1:
        return True
    global _sample_counter
    with _sample_lock:
        _sample_counter += 1
        return _sample_counter % rate == 0


# ---------------------------------------------------------------------------
# Sensitive Data Redaction
# ---------------------------------------------------------------------------

# Patterns that look like secrets: UUIDs, bearer tokens, api_key params
_REDACT_PATTERNS = [
    # UUID-shaped strings (API keys)
    re.compile(
        r'(?i)(?:api[_-]?key|token|secret|authorization|bearer)'
        r'["\']?\s*[:=]\s*["\']?'
        r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
    ),
    # Bearer tokens in Authorization headers
    re.compile(r'(?i)bearer\s+([a-zA-Z0-9._~+/=-]{8,})'),
    # Query string api_key=...
    re.compile(r'(?i)api_key=([^&\s"\'}]+)'),
    # Bare UUID that might be an API key (only in log messages, not req IDs)
    re.compile(
        r'(?<![0-9a-f])([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?![0-9a-f])'
    ),
]


def redact_sensitive(message: str) -> str:
    """
    Mask sensitive tokens in a log message string.

    Replaces UUIDs, bearer tokens, and ``api_key`` query-string values
    with ``***REDACTED***``.
    """
    for pattern in _REDACT_PATTERNS:
        message = pattern.sub(
            lambda m: m.group(0).replace(m.group(1), "***REDACTED***") if m.lastindex else "***REDACTED***",
            message,
        )
    return message


# ---------------------------------------------------------------------------
# Sensitive Filter (attached to all handlers)
# ---------------------------------------------------------------------------

class SensitiveFilter(logging.Filter):
    """Logging filter that redacts sensitive data from all log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_sensitive(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: redact_sensitive(str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_sensitive(str(a)) if isinstance(a, str) else a
                    for a in record.args
                )
        return True


# ---------------------------------------------------------------------------
# JSON Formatter
# ---------------------------------------------------------------------------

class JsonFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON objects.

    Output is optimized for log aggregators (Datadog, CloudWatch,
    Render Log Streams).  Each line is a self-contained JSON doc::

        {"ts":"...","level":"INFO","logger":"proxy","msg":"...","extra":{...}}
    """

    # Keys from LogRecord that we handle explicitly
    _SKIP_KEYS = frozenset({
        "name", "msg", "args", "created", "relativeCreated",
        "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "filename", "module", "pathname", "thread", "threadName",
        "processName", "process", "levelname", "levelno", "msecs",
        "message", "taskName",
    })

    def format(self, record: logging.LogRecord) -> str:
        doc = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc)
                        .isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Merge any extra keys passed via `logger.info("...", extra={...})`
        extras = {
            k: v for k, v in record.__dict__.items()
            if k not in self._SKIP_KEYS and not k.startswith("_")
        }
        if extras:
            doc["extra"] = extras

        if record.exc_info and record.exc_info[1]:
            doc["exception"] = self.formatException(record.exc_info)

        return json.dumps(doc, default=str, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Text Formatter (development)
# ---------------------------------------------------------------------------

class CompactTextFormatter(logging.Formatter):
    """Compact single-line text format for local development."""

    def __init__(self):
        super().__init__(
            fmt="%(asctime)s [%(levelname)-.4s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_logging() -> None:
    """Configure root logging.  Called once at startup; idempotent."""
    global _configured
    with _log_lock:
        if _configured:
            return

        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        log_format = os.getenv("LOG_FORMAT", "json").lower()

        root = logging.getLogger()
        root.setLevel(getattr(logging, log_level, logging.INFO))

        # Remove any pre-existing handlers
        root.handlers.clear()

        handler = logging.StreamHandler()  # stdout
        handler.addFilter(SensitiveFilter())

        if log_format == "json":
            handler.setFormatter(JsonFormatter())
        else:
            handler.setFormatter(CompactTextFormatter())

        root.addHandler(handler)

        # Silence noisy third-party loggers in production
        for noisy in ("werkzeug", "urllib3", "websocket", "engineio"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

        _configured = True


def get_logger(name: str = "gateway") -> logging.Logger:
    """
    Return a named logger instance.

    The first call triggers ``setup_logging()`` to configure the root
    format.  Subsequent calls return immediately.

    Args:
        name: Logger name (defaults to ``gateway``).
    """
    setup_logging()
    return logging.getLogger(name)
