"""
Tunnel Gateway — entry point.

Creates the Flask application using the factory and starts the
development server.  In production, point a WSGI server (e.g. gunicorn)
at ``gateway.app:create_app()`` instead of running this file directly.

    gunicorn "gateway.app:create_app()" --bind 0.0.0.0:5000 --threads 4
"""

from gateway.app import create_app
from gateway.config.settings import HOST, PORT, STREAMING_THRESHOLD_BYTES
from gateway.protocol.constants import SERVER_VERSION
from gateway.utils.log import get_logger

logger = get_logger()

app = create_app()

if __name__ == "__main__":
    logger.info(f"Starting Secure Gateway v{SERVER_VERSION} on {HOST}:{PORT}")
    logger.info(f"Dual Protocol Threshold: {STREAMING_THRESHOLD_BYTES} bytes")
    app.run(host=HOST, port=PORT, threaded=True)