"""
Prometheus Metrics Registry.

Defines all standard metrics exposed by the gateway at /metrics.
These metrics provide observability for active connections, 
request throughput, and bandwidth usage.
"""

from prometheus_client import Counter, Gauge, Histogram, generate_latest

# Gauges for current state
ACTIVE_TUNNELS = Gauge("gateway_active_tunnels", "Number of active websocket tunnels")
ACTIVE_REQUESTS = Gauge("gateway_active_requests", "Number of currently processing HTTP requests")

# Counters for totals
REQUESTS_TOTAL = Counter("gateway_requests_total", "Total proxy requests processed", ["status"])
BYTES_UPLOADED = Counter("gateway_bytes_uploaded_total", "Total bytes uploaded to tunnels")
BYTES_DOWNLOADED = Counter("gateway_bytes_downloaded_total", "Total bytes downloaded from tunnels")

# Histograms for latency
REQUEST_LATENCY = Histogram("gateway_request_latency_seconds", "Request latency in seconds")

def get_metrics_text() -> bytes:
    """Return the current metrics formatted for Prometheus."""
    return generate_latest()
