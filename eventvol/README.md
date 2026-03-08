# EventVol Intelligence MCP Server

A Model Context Protocol (MCP) server that provides statistical analysis of FX volatility around macro economic events.

## Features

- Analyze expected price deviations for FX pairs during macro events (NFP, CPI, FOMC, etc.)
- Calculate breakout and fakeout probabilities
- Determine volatility regimes
- Support for multiple FX pairs and events
## HTTP/SSE Transport & Deployment

This server now uses a FastAPI + Server-Sent Events transport and can be deployed to
Railway, Render, Fly.io, or any Python host. The following endpoints are available:

- `GET /` → tool metadata JSON (name, tools, pricing)
- `GET /health` → health check (`{"status": "ok"}`)
- `GET /sse` → opens SSE stream for MCP communication
- `POST /messages` → accepts MCP JSON-RPC messages

Use environment variables:

```bash
TWELVE_DATA_API_KEY=your_key_here
PORT=8000  # default
```

Include a `Procfile` (`web: python server.py`) and optional `runtime.txt` (`python-3.11.9`)
when deploying. Add `.env` to `.gitignore` to avoid leaking your API key.
## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up your Twelve Data API key in `.env`:
   ```
   TWELVE_DATA_API_KEY=your_actual_api_key
   ```

- Run the server locally (stdio for Claude Desktop):
   ```bash
   python server.py
   ```
- Or start HTTP/SSE server for deployment:
   ```bash
   # server now serves FastAPI endpoints on PORT (default 8000)
   python server.py
   ```

4. Configure Claude Desktop by adding the server to your `claude_desktop_config.json`.

## Usage

Once integrated with Claude Desktop, you can ask questions like:
- "What is the expected volatility for GBPUSD during NFP?"
- "Scan volatility regimes for EURUSD, GBPUSD, USDJPY on CPI"

## Tools

- `event_volatility_projection`: Core analysis for a single pair and event
- `volatility_regime_scan`: Scan multiple pairs for current regimes
- `list_supported_events`: List all supported events and pairs