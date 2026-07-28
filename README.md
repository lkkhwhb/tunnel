# Tunnel Gateway

A modular WebSocket-based reverse proxy that tunnels HTTP requests through authenticated WebSocket connections to local development servers.

## Overview

Tunnel Gateway acts as a public-facing relay. Client SDKs establish persistent WebSocket tunnels, and the gateway forwards incoming HTTP requests through those tunnels using a dual-mode protocol (single-message for small payloads, streaming for large ones). All tunnels are authenticated via API key and multiplexed over a single WebSocket connection per registered path.

## Architecture

```
                  ┌──────────────────────────────────────────────────┐
  HTTP Request    │              Tunnel Gateway                      │
 ──────────────►  │  ┌────────┐   ┌──────────┐   ┌───────────────┐  │   WebSocket
                  │  │ Proxy  │──►│ Tunnel   │──►│   WebSocket   │──────►  Client SDK
                  │  │ Route  │   │ Manager  │   │   Tunnel      │  │     (local server)
                  │  └────────┘   └──────────┘   └───────────────┘  │
 ◄──────────────  │       ▲            │               │            │
  HTTP Response   │       └────────────┴───────────────┘            │
                  │          Response Multiplexer                    │
                  └──────────────────────────────────────────────────┘
```

## Project Structure

```
├── main.py                        # Entry point
├── requirements.txt               # Dependencies
├── gateway/
│   ├── app.py                     # Flask app factory
│   ├── extensions.py              # Flask extension instances
│   ├── config/
│   │   └── settings.py            # Environment variables & constants
│   ├── protocol/
│   │   ├── constants.py           # Message types & version IDs
│   │   └── messages.py            # Message builder functions
│   ├── models/
│   │   ├── tunnel.py              # TunnelConnection class
│   │   ├── request.py             # RequestState class
│   │   └── stats.py               # ServerStats class
│   ├── services/
│   │   ├── __init__.py            # Service container (DI)
│   │   ├── tunnel_manager.py      # Tunnel registry
│   │   ├── request_manager.py     # Pending request registry
│   │   └── heartbeat.py           # Background ping/reap worker
│   ├── routes/
│   │   ├── admin.py               # /admin/* endpoints
│   │   ├── wake.py                # /wake endpoint
│   │   └── proxy.py               # Catch-all HTTP proxy
│   ├── websocket/
│   │   └── tunnel.py              # WebSocket tunnel handler
│   └── utils/
│       ├── auth.py                # API key verification
│       ├── encoding.py            # Base64 helpers
│       └── log.py                 # Logger configuration
└── docs/
    ├── architecture.md            # Detailed architecture & diagrams
    ├── protocol.md                # Full protocol specification
    └── sdk.md                     # SDK integration guide
```

## Deployment (Render.com)

Tunnel Gateway is fully optimized for deployment on Render's Web Service platform using Gunicorn.

**Render Settings:**
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn -c gunicorn.conf.py main:app`
- **Environment Variables:**
  - `TUNNEL_API_KEY`: Your secure secret API key (Required).
  - `PYTHON_VERSION`: `3.10.0` or higher (Recommended).
  - `PORT`: `5000` (Render handles this automatically).
  - `WEB_CONCURRENCY`: Adjust based on Render tier (defaults to CPU heuristic).

## Quick Start

```bash
pip install -r requirements.txt
python main.py
```

The server starts on `0.0.0.0:5000` by default. Configure via environment variables (see [docs/architecture.md](docs/architecture.md#environment-variables)).

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | Component design, dependency flow, environment variables |
| [Protocol](docs/protocol.md) | WebSocket message types, request lifecycle, sequence diagrams |
| [SDK Guide](docs/sdk.md) | Integration expectations, versioning, future roadmap |

## API Summary

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/<path>` | ANY | Proxy — forwards to matching tunnel |
| `/ws/tunnel` | WS | Tunnel registration & multiplexer |
| `/wake` | GET | Liveness probe |
| `/admin/status` | GET | Server stats & active tunnels |
| `/admin/health` | GET | CPU, memory, thread metrics |
| `/metrics` | GET | Prometheus compatible metrics export |
| `/admin/info` | GET | Version & capability flags |
