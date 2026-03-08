# ╔══════════════════════════════════════════════════════════════════════╗
# ║   MASTER BUILD PROMPT — EventVol Intelligence MCP Server            ║
# ║   Event-Adjusted FX Volatility Projection Engine                    ║
# ╚══════════════════════════════════════════════════════════════════════╝

## CONTEXT
You are building a production-grade Python MCP (Model Context Protocol) server called
"EventVol Intelligence". This tool gives AI assistants the ability to answer:

  "Given an upcoming macro event (e.g. NFP, CPI, FOMC), what is the statistically
   expected price deviation, breakout probability, and fakeout probability for a
   given FX pair?"

This unbundles a specific feature from Bloomberg Terminal / Refinitiv Eikon and
makes it available at $0.10/query via MCP.

---

## TECH STACK
- Language: Python 3.11+
- MCP Framework: `mcp` (Anthropic's official Python MCP SDK)
- Data API: Twelve Data (https://twelvedata.com) — OHLCV + time series
- Transport: stdio (for Claude Desktop / Cursor / Windsurf integration)
- Config: `.env` file for `TWELVE_DATA_API_KEY`

---

## PROJECT STRUCTURE
```
eventvol/
├── server.py           # Main MCP server (all logic here)
├── requirements.txt    # mcp, httpx, python-dotenv
├── .env                # TWELVE_DATA_API_KEY=xxx
├── claude_desktop_config.json  # MCP config for Claude Desktop
└── README.md
```

---

## MCP TOOLS TO IMPLEMENT

### Tool 1: `event_volatility_projection`
**The core tool.** Given a pair + event, return structured volatility intelligence.

Input schema:
```json
{
  "pair": "GBPUSD",         // FX pair e.g. EURUSD, USDJPY, GBPUSD
  "event": "NFP",           // NFP | CPI | FOMC | ECB | BOE | PPI | RETAIL_SALES
  "lookback_events": 24     // optional, default 24, max 48
}
```

Output schema:
```json
{
  "pair": "GBPUSD",
  "event": "NFP",
  "session_bias": "NY",
  "sample_size": 24,
  "expected_deviation_pips": 62.0,
  "mean_deviation_pips": 65.3,
  "p75_deviation_pips": 84.0,
  "h4_range_median_pips": 95.0,
  "breakout_probability": 0.63,
  "mean_reversion_probability": 0.37,
  "fakeout_likelihood_score": 0.37,
  "volatility_regime": "Expansionary",
  "confidence_score": 0.78,
  "analysis_timestamp": "2024-01-15T13:00:00Z"
}
```

### Tool 2: `volatility_regime_scan`
Scan multiple pairs at once and return their current regime.

Input: `{ "pairs": ["EURUSD", "GBPUSD", "USDJPY"], "event": "NFP" }`
Output: array of `{ pair, regime, median_dev_pips, confidence }`

### Tool 3: `list_supported_events`
Returns all supported macro events and their primary FX pairs. No inputs required.

---

## ANALYTICS ENGINE SPEC

### Step 1 — Fetch Data
- Use Twelve Data `/time_series` endpoint
- Fetch 1H OHLCV candles, outputsize=500
- Endpoint: `https://api.twelvedata.com/time_series?symbol={PAIR}&interval=1h&outputsize=500&apikey={KEY}`

### Step 2 — Identify Event Candles
Each event fires at a known UTC hour:
```
NFP          → 13:00 UTC (first Friday of month)
CPI          → 13:00 UTC
FOMC         → 19:00 UTC
ECB          → 13:00 UTC
BOE          → 12:00 UTC
PPI          → 13:00 UTC
RETAIL_SALES → 13:00 UTC
```
Scan candles for those matching the target hour. Take at most 1 candle per day
(enforce minimum gap of 20 candles between detections). Collect up to `lookback_events`.

### Step 3 — Compute Stats Per Event
For each detected event candle at index `i`:
- **1H range** = high–low across candles `[i, i+1]`, converted to pips
- **4H range** = high–low across candles `[i, i+4]`, converted to pips
- **Direction** = 1 if close[i+4] > open[i] else -1
- **Breakout** = H1 direction == H4 direction
- **Fakeout** = H1 direction != H4 direction

### Step 4 — Aggregate
- `expected_deviation_pips` = median of 1H ranges
- `p75_deviation_pips` = 75th percentile of 1H ranges
- `mean_deviation_pips` = mean of 1H ranges
- `h4_range_median_pips` = median of 4H ranges
- `breakout_probability` = breakouts / total
- `mean_reversion_probability` = fakeouts / total
- `fakeout_likelihood_score` = same as mean_reversion_probability

### Step 5 — Regime Classification
```
recent_avg = mean of last 5 event 1H ranges
if recent_avg < historical_mean * 0.75  → "Compressed"
if recent_avg > historical_mean * 1.30  → "Expansionary"
else                                     → "Normal"
```

### Step 6 — Confidence Score
```
sample_score   = min(sample_size / 24, 1.0)
variance_score = max(0, 1 - (stdev / mean))
confidence     = (sample_score * 0.6) + (variance_score * 0.4)
```

### Pip Size Rules
```
JPY pairs  → 0.01
XAUUSD     → 0.10
All others → 0.0001
```

---

## SESSION CLASSIFICATION
```
Asia    → 00:00–08:00 UTC
London  → 08:00–13:00 UTC
NY      → 13:00–21:00 UTC
Overlap → 12:00–16:00 UTC
```

---

## ERROR HANDLING REQUIREMENTS
- Wrap all Twelve Data calls in try/except
- If API returns no `values` key → raise ValueError with the API message
- If fewer than 5 event indices found → return error JSON, do not crash
- All tool responses return TextContent with JSON string (never raise uncaught exceptions)
- Use httpx.AsyncClient with timeout=15s

---

## ENVIRONMENT SETUP
```bash
# Install dependencies
pip install mcp httpx python-dotenv

# .env file
TWELVE_DATA_API_KEY=your_key_here

# Run server
python server.py
```

## Claude Desktop Integration
Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "eventvol-intelligence": {
      "command": "python",
      "args": ["/absolute/path/to/eventvol/server.py"],
      "env": { "TWELVE_DATA_API_KEY": "your_key_here" }
    }
  }
}
```

---

## EXAMPLE USAGE (once connected to Claude Desktop)
```
User: "Use event_volatility_projection for GBPUSD on NFP"

Claude returns:
{
  "pair": "GBPUSD",
  "event": "NFP",
  "session_bias": "NY",
  "expected_deviation_pips": 62.0,
  "p75_deviation_pips": 84.0,
  "breakout_probability": 0.63,
  "mean_reversion_probability": 0.37,
  "fakeout_likelihood_score": 0.37,
  "volatility_regime": "Expansionary",
  "confidence_score": 0.78
}
```

---

## QUALITY REQUIREMENTS
- All async — use `asyncio` and `httpx.AsyncClient` throughout
- MCP server must use `stdio_server` transport
- Server name: `"eventvol-intelligence"`
- No blocking I/O anywhere
- Keep all logic in `server.py` (single file)
- Python 3.11+ type hints throughout
- JSON responses always use `indent=2`

---

## MONETISATION NOTE (for context)
This tool is designed to be deployed as a paid MCP tool at ~$0.10/query,
replacing Bloomberg Terminal / Refinitiv Eikon event risk modules costing
$600–$3,000+/year. Target users: retail FX traders, prop traders, small funds.
