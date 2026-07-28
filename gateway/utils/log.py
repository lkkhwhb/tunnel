"""
Centralized logging configuration.

Provides a pre-configured logger for the tunnel gateway application.
All modules should use ``get_logger()`` to obtain their logger instance
rather than calling ``logging.getLogger()`` directly.
"""

import logging

_configured = False


def setup_logging():
    """Configure the root logging format and level.  Called once at startup."""
    global _configured
    if not _configured:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - [%(levelname)s] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        _configured = True


def get_logger(name: str = "ProxyBackend"):
    """
    Return a named logger instance.

    The first call triggers ``setup_logging()`` to configure the root
    format.  Subsequent calls return immediately.

    Args:
        name: Logger name (defaults to ``ProxyBackend``).
    """
    setup_logging()
    return logging.getLogger(name)
