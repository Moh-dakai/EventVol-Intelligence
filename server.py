import asyncio
import json
import os
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx
import uvicorn
from ctxprotocol import ContextError, is_protected_mcp_method, verify_context_request
from dotenv import load_dotenv
from mcp import Tool
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

# Load environment variables
load_dotenv()

# Constants
EVENT_SCHEDULES = {
    "NFP": {
        "day": "first_friday",
        "utc_hour": 13,
        "pairs": ["EURUSD", "GBPUSD", "USDJPY", "USDCAD"],
        "frequency": "monthly",
        "fetch_interval": "1day",
        "fetch_outputsize": 500,
    },
    "CPI": {
        "day": "variable",
        "utc_hour": 13,
        "pairs": ["EURUSD", "GBPUSD", "USDJPY"],
        "frequency": "monthly",
        "fetch_interval": "1day",
        "fetch_outputsize": 500,
    },
    "FOMC": {
        "day": "variable",
        "utc_hour": 19,
        "pairs": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"],
        "frequency": "8x_per_year",
        "fetch_interval": "1day",
        "fetch_outputsize": 500,
    },
    "ECB": {
        "day": "variable",
        "utc_hour": 13,
        "pairs": ["EURUSD", "EURGBP", "EURJPY"],
        "frequency": "8x_per_year",
        "fetch_interval": "1day",
        "fetch_outputsize": 500,
    },
    "BOE": {
        "day": "variable",
        "utc_hour": 12,
        "pairs": ["GBPUSD", "EURGBP", "GBPJPY"],
        "frequency": "8x_per_year",
        "fetch_interval": "1day",
        "fetch_outputsize": 500,
    },
    "PPI": {
        "day": "variable",
        "utc_hour": 13,
        "pairs": ["EURUSD", "USDJPY"],
        "frequency": "monthly",
        "fetch_interval": "1day",
        "fetch_outputsize": 500,
    },
    "RETAIL_SALES": {
        "day": "variable",
        "utc_hour": 13,
        "pairs": ["EURUSD", "GBPUSD"],
        "frequency": "monthly",
        "fetch_interval": "1day",
        "fetch_outputsize": 500,
    },
}

EVENT_HOURS = {
    event: schedule["utc_hour"]
    for event, schedule in EVENT_SCHEDULES.items()
}

PIP_SIZES = {
    "JPY": 0.01,
    "XAUUSD": 0.10,
    "default": 0.0001
}

SUPPORTED_EVENTS = list(EVENT_SCHEDULES.keys())

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

    async def fetch_candles(
        self,
        pair: str,
        interval: str = "1day",
        outputsize: int = 500,
    ) -> List[Dict[str, Any]]:
        # Twelve Data uses different symbol formats for FX
        # EURUSD should be EUR/USD
        symbol = f"{pair[:3]}/{pair[3:]}"
        url = f"https://api.twelvedata.com/time_series"
        params = {
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize,
            "apikey": self.api_key
        }
        last_error: Exception | None = None

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=25.0) as client:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()

                if "values" not in data:
                    raise ValueError(f"API error: {data.get('message', 'No values returned')}")

                # Ensure candles are oldest -> newest for forward-looking ranges (i+1, i+4).
                values = data["values"]
                values.sort(key=lambda candle: parse_candle_datetime(candle["datetime"]))
                return values
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(attempt + 1)
                    continue
                raise ValueError("API request failed after 3 attempts") from exc
            except httpx.HTTPStatusError as exc:
                raise ValueError(f"API error: {exc.response.status_code} - {exc.response.text}") from exc
            except Exception as exc:
                raise ValueError(f"Unexpected error: {str(exc)}") from exc

        raise ValueError("API request failed after 3 attempts") from last_error


class AlreadySentResponse(Response):
    """No-op response for handlers where the transport already wrote to send()."""

    async def __call__(self, scope, receive, send) -> None:
        return

    def identify_event_candles(
        self,
        candles: List[Dict[str, Any]],
        event: str,
        lookback_events: int,
        interval: str = "1day",
    ) -> List[int]:
        schedule = EVENT_SCHEDULES[event]

        if interval == "1day":
            if event == "NFP":
                indices = [
                    i for i, candle in enumerate(candles)
                    if is_first_friday_of_month(parse_candle_datetime(candle["datetime"]))
                ]
                return indices[-lookback_events:]

            frequency = schedule.get("frequency", "monthly")
            step = 21 if frequency == "monthly" else 13
            indices = list(range(5, len(candles), step))
            return indices[-lookback_events:]

        event_hour = schedule["utc_hour"]
        indices = []
        last_day = None

        for i, candle in enumerate(candles):
            dt = parse_candle_datetime(candle["datetime"])
            hour = dt.hour

            if event == "NFP" and not is_first_friday_of_month(dt):
                continue

            if hour == event_hour:
                if last_day is None or (dt - last_day).days >= 1:
                    indices.append(i)
                    last_day = dt

        return indices[-lookback_events:]

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
        pair = pair.upper().replace("/", "")
        event = event.upper()

        if event not in EVENT_SCHEDULES:
            return {"error": f"Unsupported event: {event}"}

        if lookback_events > 48:
            lookback_events = 48

        try:
            schedule = EVENT_SCHEDULES[event]
            fetch_interval = schedule.get("fetch_interval", "1day")
            fetch_outputsize = schedule.get("fetch_outputsize", 500)

            candles = await self.fetch_candles(pair, interval=fetch_interval, outputsize=fetch_outputsize)
            event_indices = self.identify_event_candles(
                candles,
                event,
                lookback_events,
                interval=fetch_interval,
            )

            if len(event_indices) < 5:
                return {
                    "error": (
                        f"Insufficient event occurrences found ({len(event_indices)}) using "
                        f"{fetch_interval} candles."
                    )
                }

            pip_size = get_pip_size(pair)
            stats = self.compute_event_stats(candles, event_indices, pip_size)

            if "error" in stats:
                return stats

            session_bias = get_session_bias(schedule["utc_hour"])

            result = {
                "pair": pair,
                "event": event,
                "session_bias": session_bias,
                **stats,
                "data_interval": fetch_interval,
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
        return {
            "events": [
                {
                    "name": event,
                    "utc_hour": schedule["utc_hour"],
                    "primary_pairs": schedule.get("pairs", [])
                }
                for event, schedule in EVENT_SCHEDULES.items()
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
                    "data_interval": {"type": "string"},
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
    try:
        eventvol = EventVolServer()

        if name == "event_volatility_projection":
            pair = arguments["pair"]
            event = arguments["event"]
            lookback_events = arguments.get("lookback_events", 24)
            result = await eventvol.event_volatility_projection(pair, event, lookback_events)
            return result

        if name == "volatility_regime_scan":
            pairs = arguments["pairs"]
            event = arguments["event"]
            result = await eventvol.volatility_regime_scan(pairs, event)
            return {"results": result}

        if name == "list_supported_events":
            return eventvol.list_supported_events()

        return {"error": f"Unknown tool: {name}"}
    except Exception as exc:
        return {
            "error": f"Internal server error: {str(exc)}",
            "tool": name,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }


sse_transport = SseServerTransport("/messages")


async def keepalive():
    """Ping /health every 4 minutes to reduce cold-start failures on Railway."""
    await asyncio.sleep(30)
    while True:
        try:
            port = int(os.environ.get("PORT", 8000))
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.get(f"http://127.0.0.1:{port}/health")
        except Exception:
            pass
        await asyncio.sleep(240)


async def start_keepalive():
    asyncio.create_task(keepalive())


async def handle_root(request: Request):
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


async def handle_health(request: Request):
    return JSONResponse({"status": "ok"})


async def handle_sse(request: Request):
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await mcp_server.run(
            streams[0], streams[1],
            mcp_server.create_initialization_options()
        )
    # Return an empty response after SSE disconnect so Starlette has a response object.
    return Response()


async def handle_messages(request: Request):
    """Handle MCP JSON-RPC messages with Context Protocol auth on tool calls."""
    body_bytes = await request.body()

    try:
        body_json = json.loads(body_bytes)
        method = body_json.get("method", "")
    except Exception:
        method = ""
        body_json = {}

    if is_protected_mcp_method(method):
        try:
            await verify_context_request(
                authorization_header=request.headers.get("authorization", "")
            )
        except ContextError as exc:
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32001,
                        "message": f"Unauthorized: {exc.message}",
                    },
                    "id": body_json.get("id"),
                },
                status_code=401,
            )

    async def receive():
        return {
            "type": "http.request",
            "body": body_bytes,
            "more_body": False,
        }

    await sse_transport.handle_post_message(
        request.scope,
        receive,
        request._send,
    )
    return AlreadySentResponse()


app = Starlette(
    routes=[
        Route("/", handle_root),
        Route("/health", handle_health),
        Route("/sse", handle_sse),
        Route("/messages", handle_messages, methods=["POST"]),
    ],
    on_startup=[start_keepalive],
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
