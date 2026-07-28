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

import psutil
from flask import Blueprint, jsonify

from gateway.extensions import limiter
from gateway import services as svc
from gateway.protocol.constants import SERVER_VERSION, PROTOCOL_VERSION

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin/status", methods=["GET"])
@limiter.exempt
def admin_status():
    """Return server status including all active tunnels and aggregate stats."""
    tunnels_info = svc.tunnel_manager.get_tunnels_info()
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
        "active_tunnels_count": len(tunnels_info),
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
    active_tunnels_count = svc.tunnel_manager.count()

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
