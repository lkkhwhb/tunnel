"""
Application factory.

Creates and configures the Flask application, initializes extensions,
wires service singletons into the service container, registers HTTP
route blueprints and the WebSocket tunnel handler, and starts
background workers.
"""

from flask import Flask
from flask_sock import Sock

from gateway.extensions import limiter
from gateway.models.stats import ServerStats
from gateway.services.tunnel_manager import TunnelManager
from gateway.services.request_manager import RequestManager
from gateway.services.heartbeat import HeartbeatService
from gateway import services as svc
from gateway.utils.log import get_logger

logger = get_logger()


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

    Returns:
        The configured :class:`Flask` application instance.
    """
    app = Flask(__name__)

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
