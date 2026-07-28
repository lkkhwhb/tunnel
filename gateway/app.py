"""
Application factory.

Creates and configures the Flask application, initializes extensions,
wires service singletons into the service container, registers HTTP
route blueprints and the WebSocket tunnel handler, and starts
background workers.
"""

import uuid
import concurrent.futures

from flask import Flask, request, g
from flask_sock import Sock

from gateway.extensions import limiter
from gateway.models.stats import ServerStats
from gateway.services.tunnel_manager import TunnelManager
from gateway.services.request_manager import RequestManager
from gateway.services.heartbeat import HeartbeatService
from gateway import services as svc
from gateway.config.settings import ENVIRONMENT
from gateway.utils.log import get_logger

logger = get_logger(__name__)


def create_app() -> Flask:
    """
    Create and fully configure the Flask application.

    This function:

    1. Instantiates the Flask app and initializes extensions
       (``flask_sock``, ``flask_limiter``).
    2. Creates service singletons (:class:`TunnelManager`,
       :class:`RequestManager`, :class:`ServerStats`) and publishes
       them to the ``gateway.services`` container module.
    3. Registers HTTP route blueprints (admin, wake, proxy).
    4. Registers the WebSocket tunnel handler.
    5. Starts the :class:`HeartbeatService` background worker.
    6. Adds production hardening (request ID tracing, security headers).

    Returns:
        The configured :class:`Flask` application instance.
    """
    app = Flask(__name__)

    # ------------------------------------------------------------------ #
    # Production Hardening
    # ------------------------------------------------------------------ #
    app.config["PROPAGATE_EXCEPTIONS"] = True
    if ENVIRONMENT == "production":
        app.config["TESTING"] = False
        app.config["DEBUG"] = False

    # ------------------------------------------------------------------ #
    # Extensions
    # ------------------------------------------------------------------ #
    sock = Sock(app)
    limiter.init_app(app)

    # ------------------------------------------------------------------ #
    # Services  (published to the container for global access)
    # ------------------------------------------------------------------ #
    svc.tunnel_manager = TunnelManager()
    svc.request_manager = RequestManager()
    svc.server_stats = ServerStats()
    # Max workers = 50: This pool only runs short non-blocking tasks that write to sockets.
    svc.send_executor = concurrent.futures.ThreadPoolExecutor(max_workers=50, thread_name_prefix="WsSend")

    # ------------------------------------------------------------------ #
    # Request Lifecycle Hooks
    # ------------------------------------------------------------------ #
    @app.before_request
    def _attach_request_id():
        """Attach a unique request ID for tracing."""
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])

    @app.after_request
    def _add_response_headers(response):
        """Add tracing and security headers to every response."""
        req_id = getattr(g, "request_id", None)
        if req_id:
            response.headers["X-Request-ID"] = req_id
        if ENVIRONMENT == "production":
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
        return response

    # ------------------------------------------------------------------ #
    # HTTP Route Blueprints
    # ------------------------------------------------------------------ #
    from gateway.routes.web import web_bp
    from gateway.routes.admin import admin_bp
    from gateway.routes.wake import wake_bp
    from gateway.routes.proxy import proxy_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(wake_bp)
    app.register_blueprint(proxy_bp)

    # ------------------------------------------------------------------ #
    # WebSocket Tunnel Handler
    # ------------------------------------------------------------------ #
    from gateway.websocket.tunnel import register_tunnel_handler
    register_tunnel_handler(sock)

    # ------------------------------------------------------------------ #
    # Background Workers
    # ------------------------------------------------------------------ #
    heartbeat = HeartbeatService(svc.tunnel_manager)
    heartbeat.start()

    return app
