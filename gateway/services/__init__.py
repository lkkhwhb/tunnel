"""
Service container.

Module-level references to shared service instances, initialized by the
app factory (``gateway.app.create_app``) during startup.  This module
serves as a lightweight dependency-injection point — any module can import
it to access the live service singletons without circular imports.

Usage from any module::

    from gateway import services as svc
    svc.tunnel_manager.register(...)
    svc.server_stats.record_request_start()
"""

# Populated by gateway.app.create_app() before any request is served.
tunnel_manager = None   # type: ignore[assignment]
request_manager = None  # type: ignore[assignment]
server_stats = None     # type: ignore[assignment]
