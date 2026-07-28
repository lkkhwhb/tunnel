"""
Tunnel Gateway — entry point.

In production (Render, AWS, etc.), use Gunicorn via the Procfile:

    gunicorn "gateway.app:create_app()" -c gunicorn.conf.py

This file provides a fallback launcher for local development and
Windows environments where Gunicorn is not available.
"""

import os
import sys

from gateway.app import create_app
from gateway.config.settings import HOST, PORT, STREAMING_THRESHOLD_BYTES, ENVIRONMENT
from gateway.protocol.constants import SERVER_VERSION
from gateway.utils.log import get_logger

logger = get_logger(__name__)

app = create_app()

if __name__ == "__main__":
    logger.info(
        "server_starting",
        extra={
            "version": SERVER_VERSION,
            "host": HOST,
            "port": PORT,
            "environment": ENVIRONMENT,
            "streaming_threshold": STREAMING_THRESHOLD_BYTES,
        },
    )

    try:
        from waitress import serve
        logger.info("using_waitress_server", extra={"server": "production"})
        serve(app, host=HOST, port=PORT, threads=8)
    except ImportError:
        logger.warning(
            "waitress_not_available_using_flask_dev",
            extra={"hint": "Install waitress or use gunicorn for production"},
        )
        app.run(host=HOST, port=PORT, threaded=True)