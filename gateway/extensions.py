"""
Flask extension instances.

Extensions are created here and initialized with the Flask app
in the app factory (``gateway.app.create_app``).  Placing them in
a dedicated module avoids circular imports between the factory
and the route / websocket modules that reference them.

Production note
---------------
The in-memory storage backend is fine for single-process deployments
(e.g. Render free tier). For multi-process Gunicorn with shared rate
limiting, switch to ``redis://`` and add ``redis`` to requirements.
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from gateway.config.settings import RATE_LIMIT_DEFAULT

limiter = Limiter(
    get_remote_address,
    default_limits=[RATE_LIMIT_DEFAULT],
    storage_uri="memory://",
)
