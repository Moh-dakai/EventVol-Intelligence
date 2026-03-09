# EventVol Intelligence MCP Server

A Model Context Protocol (MCP) server that provides statistical analysis of FX volatility around macro economic events.

## Features

- Analyze expected price deviations for FX pairs during macro events (NFP, CPI, FOMC, etc.)
- Calculate breakout and fakeout probabilities
- Determine volatility regimes
- Support multiple FX pairs and events

## HTTP/SSE Transport & Deployment

This server uses a FastAPI + Server-Sent Events transport and can be deployed to Railway, Render, Fly.io, or any Python host.

Available endpoints:

- `GET /` -> tool metadata JSON (name, tools, pricing)
- `GET /health` -> health check (`{"status": "ok"}`)
- `GET /sse` -> opens SSE stream for MCP communication
- `POST /messages` -> accepts MCP JSON-RPC messages

Environment variables:

```bash
TWELVE_DATA_API_KEY=your_key_here
PORT=8000  # default
```

Include a `Procfile` (`web: python server.py`) and optional `runtime.txt` (`python-3.11.9`) when deploying.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set up your Twelve Data API key in `.env`:
   ```
   TWELVE_DATA_API_KEY=your_actual_api_key
   ```
3. Run the server locally (HTTP/SSE):
   ```bash
   python server.py
   ```
4. Configure your MCP client to connect to the `/sse` and `/messages` endpoints.

## Usage

Once integrated with an MCP client, you can ask questions like:

- "What is the expected volatility for GBPUSD during NFP?"
- "Scan volatility regimes for EURUSD, GBPUSD, USDJPY on CPI"

## Tools

- `event_volatility_projection`: Core analysis for a single pair and event
- `volatility_regime_scan`: Scan multiple pairs for current regimes
- `list_supported_events`: List all supported events and pairs
