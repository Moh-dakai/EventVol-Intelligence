# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  MASTER PROMPT — Convert EventVol MCP Server to HTTP/SSE Transport     ║
# ║  Target Platform: Context Protocol Marketplace (ctxprotocol.com)        ║
# ╚══════════════════════════════════════════════════════════════════════════╝

## OBJECTIVE
Convert the existing EventVol Intelligence MCP server from stdio transport
to HTTP/SSE (Server-Sent Events) transport so it can be:
1. Deployed to a cloud host (Railway / Render / Fly.io)
2. Registered on Context Protocol marketplace at ctxprotocol.com
3. Called by AI agents over the internet at a public URL

---

## CURRENT STATE
The existing server.py uses stdio transport:
```python
from mcp.server.stdio import stdio_server

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())
```
This only works locally. It must be replaced with an HTTP/SSE server.

---

## TARGET ARCHITECTURE

Replace stdio with a FastAPI + SSE HTTP server that:
- Exposes a `GET /sse` endpoint → opens SSE stream for MCP communication
- Exposes a `POST /messages` endpoint → receives MCP JSON-RPC messages
- Exposes a `GET /health` endpoint → returns 200 OK (for deployment health checks)
- Exposes a `GET /` endpoint → returns tool metadata JSON (for Context Protocol listing)
- Runs on `0.0.0.0` port from `PORT` env var (default 8000)

---

## EXACT IMPLEMENTATION INSTRUCTIONS

### Step 1 — Update requirements.txt
```
mcp>=1.0.0
httpx>=0.27.0
python-dotenv>=1.0.0
fastapi>=0.111.0
uvicorn>=0.30.0
sse-starlette>=1.8.0
```

### Step 2 — Rewrite server.py entry point

Replace the stdio main() with this FastAPI + SSE pattern:

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from mcp.server.sse import SseServerTransport
import uvicorn

# Keep all existing tool logic unchanged (fetch_ohlcv, compute_event_stats,
# find_event_candle_indices, EVENT_SCHEDULES, pip sizes, session classifier,
# list_tools handler, call_tool handler — ALL unchanged)

# Replace only the FastAPI app setup and main() at the bottom:

fastapi_app = FastAPI(title="EventVol Intelligence", version="1.0.0")
sse_transport = SseServerTransport("/messages")

@fastapi_app.get("/")
async def root():
    return JSONResponse({
        "name": "EventVol Intelligence",
        "description": "Event-Adjusted FX Volatility Projection Engine. Provides expected pip deviation, breakout probability, fakeout score, and volatility regime for FX pairs around macro events (NFP, CPI, FOMC, ECB, BOE).",
        "version": "1.0.0",
        "tools": [
            "event_volatility_projection",
            "volatility_regime_scan",
            "list_supported_events"
        ],
        "pricing": "$0.10 per response",
        "author": "EventVol"
    })

@fastapi_app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})

@fastapi_app.get("/sse")
async def sse_endpoint(request: Request):
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await mcp_server.run(
            streams[0], streams[1],
            mcp_server.create_initialization_options()
        )

@fastapi_app.post("/messages")
async def messages_endpoint(request: Request):
    await sse_transport.handle_post_message(
        request.scope, request.receive, request._send
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(fastapi_app, host="0.0.0.0", port=port)
```

NOTE: Rename the MCP `Server` instance from `app` to `mcp_server` to avoid
collision with the FastAPI `fastapi_app`. Update all `@app.list_tools()` and
`@app.call_tool()` decorators to `@mcp_server.list_tools()` and
`@mcp_server.call_tool()` accordingly.

---

### Step 3 — Environment variables needed
```
TWELVE_DATA_API_KEY=your_key_here
PORT=8000                          # set automatically by Railway/Render
```

---

### Step 4 — Add Procfile (for Railway / Render)
Create a file named `Procfile` (no extension) in the project root:
```
web: python server.py
```

---

### Step 5 — Add runtime.txt (optional but recommended)
```
python-3.11.9
```

---

## DEPLOYMENT INSTRUCTIONS (Railway — recommended)

1. Push project to a GitHub repo
2. Go to railway.app → New Project → Deploy from GitHub repo
3. Add environment variable: `TWELVE_DATA_API_KEY=your_key`
4. Railway auto-detects Python + Procfile and deploys
5. Railway provides a public URL like: `https://eventvol-production.up.railway.app`

## DEPLOYMENT INSTRUCTIONS (Render — alternative)

1. Push to GitHub
2. Go to render.com → New Web Service → Connect repo
3. Build command: `pip install -r requirements.txt`
4. Start command: `python server.py`
5. Add env var: `TWELVE_DATA_API_KEY=your_key`
6. Deploy → get public URL

---

## CONTEXT PROTOCOL REGISTRATION (after deployment)

Once deployed and your public URL is live:

1. Go to https://ctxprotocol.com
2. Navigate to "List a Tool" / Builder dashboard
3. Enter your MCP endpoint URL:
   `https://your-deployed-url.railway.app/sse`
4. Set price: `$0.10 per response` (or $0.05 to attract early users)
5. Tool name: `EventVol Intelligence`
6. Description: "Event-Adjusted FX Volatility Projection Engine — returns
   expected pip deviation, breakout probability, fakeout score, and volatility
   regime for any FX pair around macro events (NFP, CPI, FOMC, ECB, BOE).
   Replaces Bloomberg Terminal event risk modules."
7. Submit — Context Protocol will verify your /sse endpoint responds correctly

---

## ENDPOINT VERIFICATION CHECKLIST
Before registering, confirm these all return correct responses:

| Endpoint | Method | Expected |
|---|---|---|
| `/` | GET | JSON with name, tools, pricing |
| `/health` | GET | `{"status": "ok"}` |
| `/sse` | GET | SSE stream opens (text/event-stream) |
| `/messages` | POST | Accepts MCP JSON-RPC |

Test with:
```bash
curl https://your-url.railway.app/health
curl https://your-url.railway.app/
```

---

## FINAL FILE STRUCTURE
```
eventvol/
├── server.py           # Updated with FastAPI + SSE transport
├── requirements.txt    # Updated with fastapi, uvicorn, sse-starlette
├── Procfile            # web: python server.py
├── runtime.txt         # python-3.11.9
├── .env                # TWELVE_DATA_API_KEY (never commit this)
├── .gitignore          # include .env
└── README.md
```

---

## .gitignore (important — never expose your API key)
```
.env
__pycache__/
*.pyc
.DS_Store
```

---

## QUALITY REQUIREMENTS
- All existing tool logic (analytics engine, pip calculations, regime
  classification, confidence scoring) must remain 100% unchanged
- Only the transport layer changes (stdio → FastAPI/SSE)
- Server must start cleanly with just: `python server.py`
- No hardcoded ports — always read from `PORT` env var
- All endpoints must handle errors gracefully and never crash the server
- Keep everything in a single server.py file
