import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx
from dotenv import load_dotenv
from mcp import Tool
from mcp.server import Server
import statistics

# HTTP/SSE transport imports
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from mcp.server.sse import SseServerTransport
from starlette.types import Receive, Scope, Send
import uvicorn

# Load environment variables
load_dotenv()

# Constants
EVENT_HOURS = {
    "NFP": 13,
    "CPI": 13,
    "FOMC": 19,
    "ECB": 13,
    "BOE": 12,
    "PPI": 13,
    "RETAIL_SALES": 13
}

PIP_SIZES = {
    "JPY": 0.01,
    "XAUUSD": 0.10,
    "default": 0.0001
}

SUPPORTED_EVENTS = list(EVENT_HOURS.keys())

def parse_candle_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

def get_pip_size(pair: str) -> float:
    if "JPY" in pair:
        return PIP_SIZES["JPY"]
    elif pair == "XAUUSD":
        return PIP_SIZES["XAUUSD"]
    else:
        return PIP_SIZES["default"]

def get_session_bias(hour: int) -> str:
    if 0 <= hour < 8:
        return "Asia"
    elif 8 <= hour < 12:
        return "London"
    elif 12 <= hour < 16:
        return "Overlap"  # London/NY overlap
    elif 16 <= hour < 21:
        return "NY"
    else:
        return "AfterHours"

def is_first_friday_of_month(dt: datetime) -> bool:
    # Check if it's Friday and the first Friday of the month
    if dt.weekday() != 4:  # 0=Monday, 4=Friday
        return False
    # Check if it's the first Friday: day <= 7
    return dt.day <= 7

class EventVolServer:
    def __init__(self):
        self.api_key = os.getenv("TWELVE_DATA_API_KEY")
        if not self.api_key:
            raise ValueError("TWELVE_DATA_API_KEY not found in environment")

    async def fetch_candles(self, pair: str) -> List[Dict[str, Any]]:
        # Twelve Data uses different symbol formats for FX
        # EURUSD should be EUR/USD
        symbol = f"{pair[:3]}/{pair[3:]}"
        url = f"https://api.twelvedata.com/time_series"
        params = {
            "symbol": symbol,
            "interval": "1h",
            "outputsize": 500,
            "apikey": self.api_key
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                if "values" not in data:
                    raise ValueError(f"API error: {data.get('message', 'No values returned')}")

                # Ensure candles are oldest -> newest for forward-looking ranges (i+1, i+4).
                values = data["values"]
                values.sort(key=lambda candle: parse_candle_datetime(candle["datetime"]))
                return values
            except httpx.TimeoutException:
                raise ValueError("API request timed out")
            except httpx.HTTPStatusError as e:
                raise ValueError(f"API error: {e.response.status_code} - {e.response.text}")
            except Exception as e:
                raise ValueError(f"Unexpected error: {str(e)}")

    def identify_event_candles(self, candles: List[Dict[str, Any]], event: str, lookback_events: int) -> List[int]:
        event_hour = EVENT_HOURS[event]
        indices = []
        last_day = None

        for i, candle in enumerate(candles):
            dt = parse_candle_datetime(candle["datetime"])
            hour = dt.hour

            # For NFP, only first Friday of month
            if event == "NFP" and not is_first_friday_of_month(dt):
                continue

            # Check if hour matches
            if hour == event_hour:
                # Ensure at least 20 candles gap (about 20 hours)
                if last_day is None or (dt - last_day).days >= 1:
                    indices.append(i)
                    last_day = dt
                    if len(indices) >= lookback_events:
                        break

        return indices

    def compute_event_stats(self, candles: List[Dict[str, Any]], event_indices: List[int], pip_size: float) -> Dict[str, Any]:
        if len(event_indices) < 5:
            return {
                "error": "Insufficient data: fewer than 5 event instances found",
                "sample_size": len(event_indices)
            }

        h1_ranges = []
        h4_ranges = []
        breakouts = 0
        fakeouts = 0

        for i in event_indices:
            if i + 4 >= len(candles):
                continue  # Not enough candles for 4H analysis

            # 1H range: candles i to i+1
            h1_high = max(float(candles[j]["high"]) for j in range(i, i+2) if j < len(candles))
            h1_low = min(float(candles[j]["low"]) for j in range(i, i+2) if j < len(candles))
            h1_range = (h1_high - h1_low) / pip_size
            h1_ranges.append(h1_range)

            # 4H range: candles i to i+4
            h4_high = max(float(candles[j]["high"]) for j in range(i, i+5) if j < len(candles))
            h4_low = min(float(candles[j]["low"]) for j in range(i, i+5) if j < len(candles))
            h4_range = (h4_high - h4_low) / pip_size
            h4_ranges.append(h4_range)

            # Direction: 1 if close[i+4] > open[i], else -1
            h1_direction = 1 if float(candles[i+1]["close"]) > float(candles[i]["open"]) else -1
            h4_direction = 1 if float(candles[i+4]["close"]) > float(candles[i]["open"]) else -1

            if h1_direction == h4_direction:
                breakouts += 1
            else:
                fakeouts += 1

        total = breakouts + fakeouts
        if total == 0:
            return {"error": "No valid event ranges computed"}

        # Aggregates
        expected_deviation_pips = statistics.median(h1_ranges)
        p75_deviation_pips = statistics.quantiles(h1_ranges, n=4)[2]  # 75th percentile
        mean_deviation_pips = statistics.mean(h1_ranges)
        h4_range_median_pips = statistics.median(h4_ranges) if h4_ranges else 0

        breakout_probability = breakouts / total
        mean_reversion_probability = fakeouts / total
        fakeout_likelihood_score = mean_reversion_probability

        # Regime classification
        historical_mean = mean_deviation_pips
        if len(h1_ranges) >= 5:
            recent_avg = statistics.mean(h1_ranges[-5:])
            if recent_avg < historical_mean * 0.75:
                regime = "Compressed"
            elif recent_avg > historical_mean * 1.30:
                regime = "Expansionary"
            else:
                regime = "Normal"
        else:
            regime = "Normal"

        # Confidence score
        sample_size = len(h1_ranges)
        sample_score = min(sample_size / 24, 1.0)
        if len(h1_ranges) > 1:
            stdev = statistics.stdev(h1_ranges)
            variance_score = max(0, 1 - (stdev / mean_deviation_pips))
        else:
            variance_score = 0.5  # Default if only one sample
        confidence_score = (sample_score * 0.6) + (variance_score * 0.4)

        return {
            "sample_size": sample_size,
            "expected_deviation_pips": round(expected_deviation_pips, 1),
            "mean_deviation_pips": round(mean_deviation_pips, 1),
            "p75_deviation_pips": round(p75_deviation_pips, 1),
            "h4_range_median_pips": round(h4_range_median_pips, 1),
            "breakout_probability": round(breakout_probability, 2),
            "mean_reversion_probability": round(mean_reversion_probability, 2),
            "fakeout_likelihood_score": round(fakeout_likelihood_score, 2),
            "volatility_regime": regime,
            "confidence_score": round(confidence_score, 2)
        }

    async def event_volatility_projection(self, pair: str, event: str, lookback_events: int = 24) -> Dict[str, Any]:
        if event not in EVENT_HOURS:
            return {"error": f"Unsupported event: {event}"}

        if lookback_events > 48:
            lookback_events = 48

        try:
            candles = await self.fetch_candles(pair)
            event_indices = self.identify_event_candles(candles, event, lookback_events)
            pip_size = get_pip_size(pair)
            stats = self.compute_event_stats(candles, event_indices, pip_size)

            if "error" in stats:
                return stats

            session_bias = get_session_bias(EVENT_HOURS[event])

            result = {
                "pair": pair,
                "event": event,
                "session_bias": session_bias,
                **stats,
                "analysis_timestamp": datetime.now(timezone.utc).isoformat()
            }

            return result

        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"Unexpected error: {str(e)}"}

    async def volatility_regime_scan(self, pairs: List[str], event: str) -> List[Dict[str, Any]]:
        results = []
        for pair in pairs:
            projection = await self.event_volatility_projection(pair, event, 24)
            if "error" in projection:
                results.append({
                    "pair": pair,
                    "error": projection["error"]
                })
            else:
                results.append({
                    "pair": pair,
                    "regime": projection["volatility_regime"],
                    "median_dev_pips": projection["expected_deviation_pips"],
                    "confidence": projection["confidence_score"]
                })
        return results

    def list_supported_events(self) -> Dict[str, Any]:
        # Primary pairs for each event (based on typical impact)
        primary_pairs = {
            "NFP": ["USDJPY", "EURUSD", "GBPUSD"],
            "CPI": ["EURUSD", "GBPUSD", "USDJPY"],
            "FOMC": ["EURUSD", "GBPUSD", "USDJPY"],
            "ECB": ["EURUSD", "GBPUSD", "USDCHF"],
            "BOE": ["GBPUSD", "EURGBP", "GBPJPY"],
            "PPI": ["EURUSD", "GBPUSD", "USDJPY"],
            "RETAIL_SALES": ["EURUSD", "GBPUSD", "USDJPY"]
        }

        return {
            "events": [
                {
                    "name": event,
                    "utc_hour": hour,
                    "primary_pairs": primary_pairs.get(event, [])
                }
                for event, hour in EVENT_HOURS.items()
            ]
        }

mcp_server = Server("eventvol-intelligence")

@mcp_server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="event_volatility_projection",
            description="Get volatility projection for a specific FX pair and macro event.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pair": {
                        "type": "string",
                        "description": "FX pair e.g. EURUSD, USDJPY, GBPUSD"
                    },
                    "event": {
                        "type": "string",
                        "enum": ["NFP", "CPI", "FOMC", "ECB", "BOE", "PPI", "RETAIL_SALES"],
                        "description": "Macro event"
                    },
                    "lookback_events": {
                        "type": "integer",
                        "description": "Number of past events to analyze (default 24, max 48)",
                        "default": 24
                    }
                },
                "required": ["pair", "event"]
            },
            outputSchema={
                "type": "object",
                "properties": {
                    "error": {"type": "string"},
                    "pair": {"type": "string"},
                    "event": {"type": "string"},
                    "session_bias": {"type": "string"},
                    "sample_size": {"type": "integer"},
                    "expected_deviation_pips": {"type": "number"},
                    "mean_deviation_pips": {"type": "number"},
                    "p75_deviation_pips": {"type": "number"},
                    "h4_range_median_pips": {"type": "number"},
                    "breakout_probability": {"type": "number"},
                    "mean_reversion_probability": {"type": "number"},
                    "fakeout_likelihood_score": {"type": "number"},
                    "volatility_regime": {"type": "string"},
                    "confidence_score": {"type": "number"},
                    "analysis_timestamp": {"type": "string"}
                }
            }
        ),
        Tool(
            name="volatility_regime_scan",
            description="Scan volatility regimes for multiple FX pairs for a given event.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pairs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of FX pairs to scan"
                    },
                    "event": {
                        "type": "string",
                        "enum": ["NFP", "CPI", "FOMC", "ECB", "BOE", "PPI", "RETAIL_SALES"],
                        "description": "Macro event"
                    }
                },
                "required": ["pairs", "event"]
            },
            outputSchema={
                "type": "object",
                "properties": {
                    "results": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "pair": {"type": "string"},
                                "error": {"type": "string"},
                                "regime": {"type": "string"},
                                "median_dev_pips": {"type": "number"},
                                "confidence": {"type": "number"}
                            }
                        }
                    }
                },
                "required": ["results"]
            }
        ),
        Tool(
            name="list_supported_events",
            description="List all supported macro events and their primary FX pairs.",
            inputSchema={
                "type": "object",
                "properties": {}
            },
            outputSchema={
                "type": "object",
                "properties": {
                    "events": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "utc_hour": {"type": "integer"},
                                "primary_pairs": {
                                    "type": "array",
                                    "items": {"type": "string"}
                                }
                            },
                            "required": ["name", "utc_hour", "primary_pairs"]
                        }
                    }
                },
                "required": ["events"]
            }
        )
    ]

@mcp_server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> dict:
    """Handle tool calls."""
    eventvol = EventVolServer()

    if name == "event_volatility_projection":
        pair = arguments["pair"]
        event = arguments["event"]
        lookback_events = arguments.get("lookback_events", 24)
        result = await eventvol.event_volatility_projection(pair, event, lookback_events)
        return result

    elif name == "volatility_regime_scan":
        pairs = arguments["pairs"]
        event = arguments["event"]
        result = await eventvol.volatility_regime_scan(pairs, event)
        return {"results": result}

    elif name == "list_supported_events":
        result = eventvol.list_supported_events()
        return result

    else:
        return {"error": f"Unknown tool: {name}"}

# FastAPI / SSE transport setup
fastapi_app = FastAPI(title="EventVol Intelligence", version="1.0.0")
sse_transport = SseServerTransport("/messages/")

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
    # Return an empty response after SSE disconnect to avoid FastAPI trying
    # to serialize None.
    return Response()

async def messages_asgi(scope: Scope, receive: Receive, send: Send):
    if scope["type"] == "http" and scope["method"] != "POST":
        response = Response("Method Not Allowed", status_code=405)
        await response(scope, receive, send)
        return
    await sse_transport.handle_post_message(scope, receive, send)

# Mount POST messages handler as raw ASGI app. It writes responses directly.
fastapi_app.mount("/messages/", messages_asgi)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(fastapi_app, host="0.0.0.0", port=port)
