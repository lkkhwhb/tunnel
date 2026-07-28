"""
Wake endpoint.

A lightweight liveness probe that responds immediately without
accessing any internal state.  Intended for external health-checkers
or keep-alive pings from hosting platforms.
"""

import time

from flask import Blueprint, jsonify

from gateway.extensions import limiter

wake_bp = Blueprint("wake", __name__)


@wake_bp.route("/wake", methods=["GET"])
@limiter.exempt
def wake_endpoint():
    """Return a simple ``awake`` status with a Unix timestamp."""
    return jsonify({
        "status": "awake",
        "timestamp": int(time.time()),
    })
