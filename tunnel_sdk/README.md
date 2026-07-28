# Tunnel SDK

This is the production-ready Python SDK for the Tunnel Gateway. It allows you to establish secure WebSocket tunnels and seamlessly proxy HTTP traffic to your local development server.

## Features

* **Thread-safe**: Runs in the background without blocking your main application loop. No `asyncio` required!
* **Automated Reconnection**: Built-in exponential backoff means you don't have to manually manage network hiccups.
* **Smart Streaming**: Automatically switches to chunked streaming for large files, keeping memory overhead low.
* **Context Manager**: Start and stop the tunnel cleanly using `with Tunnel.from_env() as tunnel:`.
* **Events API**: Listen to hooks like `on_connect`, `on_disconnect`, and `on_error`.

## Quick Start

Create a `.env` file in your root folder:
```env
TUNNEL_API_KEY=your-secret-key
TUNNEL_TARGET_PATH=/api
TUNNEL_PORT=5000
```

Run the tunnel:
```python
from tunnel_sdk import Tunnel

with Tunnel.from_env() as tunnel:
    # This blocks until interrupted!
    tunnel.wait()
```

When connected, you'll see a success message like:
```
============================================================
TUNNEL CONNECTED SUCCESSFULLY!
Public URL : https://your-gateway.com/api
Forwarding to : http://127.0.0.1:5000
============================================================
```

## Structure

* `client.py` - The main `Tunnel` interface.
* `connection.py` - WebSocket loop and reconnect logic.
* `dispatcher.py` - HTTP request proxying via `httpx`.
* `protocol.py` - Data structures and base64 encoders.
* `config.py` - Environment loader.

For full API reference, see `docs/sdk_reference.md` in the project root.
