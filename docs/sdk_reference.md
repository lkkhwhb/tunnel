# Tunnel SDK Reference

The Tunnel SDK provides a production-ready, thread-safe way to proxy incoming HTTP traffic from the Tunnel Gateway directly to your local development server over WebSockets.

## Installation

```bash
pip install tunnel-sdk
```

*(Note: Currently, since this is a local project, ensure `tunnel_sdk` is in your PYTHONPATH and install `httpx` and `websocket-client`)*

## Quick Start

```python
from tunnel_sdk import Tunnel

# Assumes you have TUNNEL_GATEWAY, TUNNEL_API_KEY, TUNNEL_TARGET_PATH, 
# and TUNNEL_LOCAL_URL set in your environment variables.
with Tunnel.from_env() as tunnel:
    print("Tunnel is running!")
    # Blocks forever
    tunnel.wait()
```

## Configuration

You can configure the tunnel using code, environment variables, or a mix of both.

### Environment Variables

| Variable | Description |
|----------|-------------|
| `TUNNEL_GATEWAY` | The WebSocket URL (e.g., `wss://example.com`) |
| `TUNNEL_API_KEY` | Secret API key provided by the gateway |
| `TUNNEL_TARGET_PATH` | The path prefix to intercept (e.g., `/api`) |
| `TUNNEL_LOCAL_URL` | The local destination URL (e.g., `http://127.0.0.1:5000`) |

### Constructor Parameters

```python
from tunnel_sdk import Tunnel

tunnel = Tunnel(
    gateway="wss://example.com",
    api_key="secret-key",
    target_path="/api",
    local_url="http://127.0.0.1:5000",
    max_reconnects=-1,          # -1 for infinite retries
    reconnect_base_delay=1.0,   # Seconds
    reconnect_max_delay=60.0    # Seconds
)
```

## API Reference

### `Tunnel` Class

#### `tunnel.run(local_url=None)`
Starts the tunnel connection and **blocks** the current thread until the tunnel is stopped or interrupted.

#### `tunnel.start(local_url=None)`
Starts the tunnel connection in a **background thread**. The method returns immediately.

#### `tunnel.stop()`
Gracefully stops the tunnel, closes all WebSockets, and cleanly shuts down worker threads.

#### `tunnel.restart(local_url=None)`
Convenience method to stop and restart the tunnel.

#### `tunnel.wait()`
Blocks the current thread until `tunnel.stop()` is called. Useful after calling `tunnel.start()`.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `tunnel.is_connected` | `bool` | True if the WebSocket is currently open and authenticated |
| `tunnel.protocol_version` | `str` | The negotiated protocol version (e.g., "1.0") |
| `tunnel.sdk_version` | `str` | The installed SDK version |
| `tunnel.reconnect_count` | `int` | Total number of reconnections attempted |
| `tunnel.uptime` | `float` | Seconds since the tunnel was first instantiated |
| `tunnel.statistics` | `dict` | A dictionary of live metrics (bytes up/down, active requests, etc.) |

### Event Callbacks

The SDK features a robust event emitter for tracking state changes.

```python
@tunnel.on("on_connect")
def handle_connect():
    print("Connected to Gateway!")

@tunnel.on("on_disconnect")
def handle_disconnect():
    print("Disconnected!")

@tunnel.on("on_reconnect_attempt")
def handle_reconnect(attempt_number):
    print(f"Reconnecting... Attempt {attempt_number}")

@tunnel.on("on_error")
def handle_error(exception):
    print(f"Error occurred: {exception}")

@tunnel.on("on_request_start")
def handle_req_start(req_id):
    print(f"Incoming request: {req_id}")

@tunnel.on("on_request_end")
def handle_req_end(req_id):
    print(f"Finished request: {req_id}")
```

## Exceptions

All SDK exceptions inherit from `tunnel_sdk.exceptions.TunnelError`.

- `AuthenticationError`: Invalid API Key.
- `ConnectionError`: General network failure.
- `ProtocolError`: Incompatible version or malformed JSON payloads.
- `TimeoutError`: Ping or request timeouts.
