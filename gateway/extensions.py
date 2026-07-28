"""
Flask extension instances.

Extensions are created here and initialized with the Flask app
in the app factory (``gateway.app.create_app``).  Placing them in
a dedicated module avoids circular imports between the factory
and the route / websocket modules that reference them.
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from gateway.config.settings import RATE_LIMIT_DEFAULT

limiter = Limiter(
    get_remote_address,
    default_limits=[RATE_LIMIT_DEFAULT],
    storage_uri="memory://",
)
