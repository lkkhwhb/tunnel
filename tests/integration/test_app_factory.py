"""
Integration tests for the app factory (gateway.app.create_app).

Verifies that the factory creates a fully wired application with all
extensions, services, routes, and background workers.
"""

from flask import Flask

from gateway.app import create_app
from gateway import services as svc
from gateway.services.tunnel_manager import TunnelManager
from gateway.services.request_manager import RequestManager
from gateway.models.stats import ServerStats


class TestCreateApp:
    """Tests for the create_app factory."""

    def test_returns_flask_app(self):
        app = create_app()
        assert isinstance(app, Flask)

    def test_services_initialized(self):
        create_app()
        assert isinstance(svc.tunnel_manager, TunnelManager)
        assert isinstance(svc.request_manager, RequestManager)
        assert isinstance(svc.server_stats, ServerStats)

    def test_fresh_services_each_call(self):
        create_app()
        tm1 = svc.tunnel_manager
        create_app()
        tm2 = svc.tunnel_manager
        assert tm1 is not tm2  # New instances each time


class TestRouteRegistration:
    """Verify all routes are registered."""

    def test_all_routes_present(self, app):
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        assert "/" in rules
        assert "/<path:path>" in rules
        assert "/admin/status" in rules
        assert "/admin/health" in rules
        assert "/admin/info" in rules
        assert "/wake" in rules
        assert "/ws/tunnel" in rules

    def test_proxy_accepts_all_methods(self, app):
        for rule in app.url_map.iter_rules():
            if rule.rule == "/<path:path>":
                methods = rule.methods
                for m in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                    assert m in methods

    def test_admin_routes_are_get_only(self, app):
        admin_rules = [
            r for r in app.url_map.iter_rules()
            if r.rule.startswith("/admin/")
        ]
        for rule in admin_rules:
            assert "GET" in rule.methods
            assert "POST" not in rule.methods


class TestExtensions:
    """Verify Flask extensions are initialized."""

    def test_limiter_attached(self, app):
        # Flask-Limiter registers itself in app.extensions
        assert "limiter" in app.extensions
