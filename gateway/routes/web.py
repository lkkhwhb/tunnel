"""
Web route handler.

Serves the Admin Panel SPA (index.html) at the root (/) and /admin endpoints,
along with static assets (CSS, JS, icons) from the gateway/static directory.
"""

from pathlib import Path
from flask import Blueprint, send_from_directory, abort
from gateway.extensions import limiter

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

web_bp = Blueprint("web", __name__)


@web_bp.route("/", methods=["GET"])
@web_bp.route("/admin", methods=["GET"])
@web_bp.route("/dashboard", methods=["GET"])
@web_bp.route("/index.html", methods=["GET"])
@limiter.exempt
def serve_dashboard():
    """Serve the Admin Panel SPA index.html."""
    if not STATIC_DIR.exists() or not (STATIC_DIR / "index.html").exists():
        return abort(404, description="Admin Panel UI not built or missing index.html")
    return send_from_directory(STATIC_DIR, "index.html")


@web_bp.route("/static/<path:filename>", methods=["GET"])
@limiter.exempt
def serve_static(filename):
    """Serve static assets (CSS, JS, images)."""
    if not STATIC_DIR.exists():
        return abort(404)
    return send_from_directory(STATIC_DIR, filename)
