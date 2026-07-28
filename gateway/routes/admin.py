"""
Admin route handlers.

Provides server status, health metrics, and version information
for monitoring and operational visibility.

Endpoints
---------
GET /admin/status  — Active tunnels and aggregate request stats.
GET /admin/health  — System-level health (CPU, memory, threads).
GET /admin/info    — Server version, protocol, and capability flags.
"""

import os
import sys
import platform
import socket
import threading
import secrets
import uuid

import psutil
from functools import wraps
from flask import Blueprint, jsonify, request

from gateway.extensions import limiter
from gateway import services as svc
from gateway.protocol.constants import SERVER_VERSION, PROTOCOL_VERSION
from gateway.utils.auth import (
    verify_api_key, AuthError,
    add_dummy_api_key, remove_dummy_api_key, list_dummy_api_keys, clear_dummy_api_keys
)

admin_bp = Blueprint("admin", __name__)


def _is_request_authenticated() -> bool:
    """Check if the incoming request includes a valid API key."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        api_key = auth_header[7:].strip()
    else:
        api_key = request.headers.get("X-API-Key") or request.args.get("api_key")
    if not api_key:
        return False
    try:
        verify_api_key(api_key)
        return True
    except Exception:
        return False


@admin_bp.route("/admin/status", methods=["GET"])
@limiter.exempt
def admin_status():
    """Return server status including active tunnels (only if authenticated) and aggregate stats."""
    is_auth = _is_request_authenticated()
    tunnels_info = svc.tunnel_manager.get_tunnels_info() if is_auth else []
    active_tunnels_count = len(svc.tunnel_manager.get_tunnels_info()) if is_auth else "Hidden (Auth Required)"
    stats = svc.server_stats.snapshot()

    return jsonify({
        "status": "online",
        "uptime_seconds": stats["uptime_seconds"],
        "started_at": stats["started_at"],
        "total_requests": stats["total_requests"],
        "active_requests": stats["active_requests"],
        "average_latency_ms": stats["average_latency_ms"],
        "bytes_uploaded": stats["bytes_uploaded"],
        "bytes_downloaded": stats["bytes_downloaded"],
        "total_bytes_transferred": stats["total_bytes_transferred"],
        "active_tunnels_count": active_tunnels_count,
        "tunnels": tunnels_info,
    })


@admin_bp.route("/admin/health", methods=["GET"])
@limiter.exempt
def admin_health():
    """Return system health metrics including CPU, memory, and process info."""
    mem = psutil.virtual_memory()
    pid = os.getpid()

    try:
        p = psutil.Process(pid)
        thread_count = p.num_threads()
    except Exception:
        thread_count = threading.active_count()

    stats = svc.server_stats.snapshot()
    is_auth = _is_request_authenticated()
    real_count = svc.tunnel_manager.count()
    active_tunnels_count = real_count if is_auth else "Hidden"

    return jsonify({
        "cpu_usage_percent": psutil.cpu_percent(interval=None),
        "memory_usage_percent": mem.percent,
        "used_memory_bytes": mem.used,
        "total_memory_bytes": mem.total,
        "thread_count": thread_count,
        "process_id": pid,
        "python_thread_count": threading.active_count(),
        "active_tunnels": active_tunnels_count,
        "active_requests": stats["active_requests"],
        "total_requests": stats["total_requests"],
        "bytes_uploaded": stats["bytes_uploaded"],
        "bytes_downloaded": stats["bytes_downloaded"],
        "average_latency_ms": stats["average_latency_ms"],
        "server_uptime_seconds": stats["uptime_seconds"],
        "websocket_tunnel_count": active_tunnels_count,
    })


@admin_bp.route("/admin/info", methods=["GET"])
@limiter.exempt
def admin_info():
    """Return server version and capability information."""
    stats = svc.server_stats.snapshot()

    return jsonify({
        "server_version": SERVER_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "python_version": sys.version,
        "operating_system": f"{platform.system()} {platform.release()}",
        "hostname": socket.gethostname(),
        "startup_time": stats["started_at"],
        "streaming_support": True,
        "binary_frame_support": False,
        "compression_support": False,
    })


def require_admin_key(f):
    """Decorator to require a valid API key for protected admin actions."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            api_key = auth_header[7:].strip()
        else:
            api_key = request.headers.get("X-API-Key") or request.args.get("api_key") or (request.json.get("api_key") if request.is_json and request.json else None)
        try:
            verify_api_key(api_key)
        except AuthError as e:
            return jsonify({"error": e.client_message}), 401
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route("/admin/verify", methods=["POST"])
@limiter.exempt
@require_admin_key
def admin_verify():
    """Verify an API key and return confirmation."""
    return jsonify({"status": "valid", "message": "API key verified successfully."})


@admin_bp.route("/admin/settings", methods=["GET"])
@limiter.exempt
@require_admin_key
def admin_get_settings():
    """Return current server runtime configuration settings."""
    import gateway.config.settings as settings_mod
    return jsonify({
        "streaming_threshold_bytes": settings_mod.STREAMING_THRESHOLD_BYTES,
        "chunk_size": settings_mod.CHUNK_SIZE,
        "tunnel_timeout": settings_mod.TUNNEL_TIMEOUT,
        "ping_interval": settings_mod.PING_INTERVAL,
        "ping_timeout": settings_mod.PING_TIMEOUT,
        "rate_limit_default": settings_mod.RATE_LIMIT_DEFAULT,
    })


@admin_bp.route("/admin/settings", methods=["POST"])
@limiter.exempt
@require_admin_key
def admin_update_settings():
    """Update runtime server configuration settings."""
    import gateway.config.settings as settings_mod
    data = request.get_json(silent=True) or {}

    if "streaming_threshold_bytes" in data:
        settings_mod.STREAMING_THRESHOLD_BYTES = int(data["streaming_threshold_bytes"])
    if "chunk_size" in data:
        settings_mod.CHUNK_SIZE = int(data["chunk_size"])
    if "tunnel_timeout" in data:
        settings_mod.TUNNEL_TIMEOUT = float(data["tunnel_timeout"])
    if "ping_interval" in data:
        settings_mod.PING_INTERVAL = int(data["ping_interval"])
    if "ping_timeout" in data:
        settings_mod.PING_TIMEOUT = int(data["ping_timeout"])
    if "rate_limit_default" in data:
        settings_mod.RATE_LIMIT_DEFAULT = str(data["rate_limit_default"])

    return jsonify({
        "status": "updated",
        "message": "Settings updated successfully.",
        "settings": {
            "streaming_threshold_bytes": settings_mod.STREAMING_THRESHOLD_BYTES,
            "chunk_size": settings_mod.CHUNK_SIZE,
            "tunnel_timeout": settings_mod.TUNNEL_TIMEOUT,
            "ping_interval": settings_mod.PING_INTERVAL,
            "ping_timeout": settings_mod.PING_TIMEOUT,
            "rate_limit_default": settings_mod.RATE_LIMIT_DEFAULT,
        },
    })


@admin_bp.route("/admin/tunnels", methods=["DELETE"])
@limiter.exempt
@require_admin_key
def admin_delete_tunnel():
    """Disconnect and unregister an active tunnel by target path."""
    path = request.args.get("path")
    if not path:
        return jsonify({"error": "Missing 'path' parameter"}), 400

    if not path.startswith("/"):
        path = "/" + path

    tunnel = svc.tunnel_manager.get(path)
    if not tunnel:
        return jsonify({"error": f"No active tunnel found at {path}"}), 404

    try:
        tunnel.ws.close()
    except Exception:
        pass
    svc.tunnel_manager.unregister(path)
    return jsonify({"status": "disconnected", "message": f"Tunnel {path} disconnected."})


@admin_bp.route("/admin/stats/reset", methods=["POST"])
@limiter.exempt
@require_admin_key
def admin_reset_stats():
    """Reset server telemetry statistics."""
    svc.server_stats.reset()
    return jsonify({"status": "reset", "message": "Server telemetry reset successfully."})


@admin_bp.route("/admin/keys", methods=["GET"])
@limiter.exempt
@require_admin_key
def admin_list_keys():
    """List all active dummy API keys."""
    return jsonify({
        "status": "success",
        "dummy_keys": list_dummy_api_keys(),
        "count": len(list_dummy_api_keys()),
    })


@admin_bp.route("/admin/keys", methods=["POST"])
@limiter.exempt
@require_admin_key
def admin_create_key():
    """Create a new temporary dummy API key."""
    data = request.get_json(silent=True) or {}
    custom_key = data.get("key", "").strip()
    if not custom_key:
        custom_key = "dm_" + str(uuid.uuid4())

    add_dummy_api_key(custom_key)
    return jsonify({
        "status": "created",
        "key": custom_key,
        "dummy_keys": list_dummy_api_keys(),
        "message": f"Dummy API key '{custom_key}' created in memory.",
    }), 201


@admin_bp.route("/admin/keys", methods=["DELETE"])
@limiter.exempt
@require_admin_key
def admin_delete_key():
    """Delete a temporary dummy API key."""
    key = request.args.get("key") or (request.get_json(silent=True) or {}).get("key")
    if not key:
        return jsonify({"error": "Missing 'key' parameter"}), 400

    if remove_dummy_api_key(key):
        return jsonify({
            "status": "deleted",
            "dummy_keys": list_dummy_api_keys(),
            "message": f"Dummy API key '{key}' removed from memory.",
        })
    return jsonify({"error": f"Dummy API key '{key}' not found"}), 404
