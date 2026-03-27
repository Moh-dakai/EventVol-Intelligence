import asyncio
import json
import os
import statistics
from contextlib import asynccontextmanager
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

# -----------------------------------------------------------------
# Economic Calendar  — real historical UTC release datetimes
# Format: "YYYY-MM-DDTHH:MM"  (UTC, no seconds needed)
# Sources: BLS.gov release calendar, Federal Reserve, ECB, BOE
# -----------------------------------------------------------------
EVENT_RELEASE_DATES: dict[str, dict] = {
    # ---------- NFP: first Friday of each month at 13:30 UTC ----------
    "NFP": {
        "utc_hour": 13,
        "pairs": ["EURUSD", "GBPUSD", "USDJPY", "USDCAD"],
        "releases": [
            "2022-01-07T13:30", "2022-02-04T13:30", "2022-03-04T13:30",
            "2022-04-01T13:30", "2022-05-06T13:30", "2022-06-03T13:30",
            "2022-07-08T13:30", "2022-08-05T13:30", "2022-09-02T13:30",
            "2022-10-07T13:30", "2022-11-04T13:30", "2022-12-02T13:30",
            "2023-01-06T13:30", "2023-02-03T13:30", "2023-03-10T13:30",
            "2023-04-07T13:30", "2023-05-05T13:30", "2023-06-02T13:30",
            "2023-07-07T13:30", "2023-08-04T13:30", "2023-09-01T13:30",
            "2023-10-06T13:30", "2023-11-03T13:30", "2023-12-08T13:30",
            "2024-01-05T13:30", "2024-02-02T13:30", "2024-03-08T13:30",
            "2024-04-05T13:30", "2024-05-03T13:30", "2024-06-07T13:30",
            "2024-07-05T13:30", "2024-08-02T13:30", "2024-09-06T13:30",
            "2024-10-04T13:30", "2024-11-01T13:30", "2024-12-06T13:30",
            "2025-01-10T13:30", "2025-02-07T13:30", "2025-03-07T13:30",
            "2025-04-04T13:30", "2025-05-02T13:30", "2025-06-06T13:30",
            "2025-07-03T13:30", "2025-08-01T13:30", "2025-09-05T13:30",
            "2025-10-03T13:30", "2025-11-07T13:30", "2025-12-05T13:30",
            "2026-01-09T13:30", "2026-02-06T13:30", "2026-03-06T13:30",
        ],
    },
    # ---------- CPI: variable mid-month at 13:30 UTC (BLS schedule) ----------
    "CPI": {
        "utc_hour": 13,
        "pairs": ["EURUSD", "GBPUSD", "USDJPY"],
        "releases": [
            "2022-01-12T13:30", "2022-02-10T13:30", "2022-03-10T13:30",
            "2022-04-12T13:30", "2022-05-11T13:30", "2022-06-10T13:30",
            "2022-07-13T13:30", "2022-08-10T13:30", "2022-09-13T13:30",
            "2022-10-13T13:30", "2022-11-10T13:30", "2022-12-13T13:30",
            "2023-01-12T13:30", "2023-02-14T13:30", "2023-03-14T13:30",
            "2023-04-12T13:30", "2023-05-10T13:30", "2023-06-13T13:30",
            "2023-07-12T13:30", "2023-08-10T13:30", "2023-09-13T13:30",
            "2023-10-12T13:30", "2023-11-14T13:30", "2023-12-12T13:30",
            "2024-01-11T13:30", "2024-02-13T13:30", "2024-03-12T13:30",
            "2024-04-10T13:30", "2024-05-15T13:30", "2024-06-12T13:30",
            "2024-07-11T13:30", "2024-08-14T13:30", "2024-09-11T13:30",
            "2024-10-10T13:30", "2024-11-13T13:30", "2024-12-11T13:30",
            "2025-01-15T13:30", "2025-02-12T13:30", "2025-03-12T13:30",
            "2025-04-10T13:30", "2025-05-13T13:30", "2025-06-11T13:30",
            "2025-07-15T13:30", "2025-08-12T13:30", "2025-09-10T13:30",
            "2025-10-15T13:30", "2025-11-13T13:30", "2025-12-10T13:30",
            "2026-01-14T13:30", "2026-02-12T13:30", "2026-03-11T13:30",
        ],
    },
    # ---------- FOMC: 8 meetings per year, statement at ~19:00 UTC ----------
    "FOMC": {
        "utc_hour": 19,
        "pairs": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"],
        "releases": [
            "2022-01-26T19:00", "2022-03-16T19:00", "2022-05-04T19:00",
            "2022-06-15T19:00", "2022-07-27T19:00", "2022-09-21T19:00",
            "2022-11-02T19:00", "2022-12-14T19:00",
            "2023-02-01T19:00", "2023-03-22T19:00", "2023-05-03T19:00",
            "2023-06-14T19:00", "2023-07-26T19:00", "2023-09-20T19:00",
            "2023-11-01T19:00", "2023-12-13T19:00",
            "2024-01-31T19:00", "2024-03-20T19:00", "2024-05-01T19:00",
            "2024-06-12T19:00", "2024-07-31T19:00", "2024-09-18T19:00",
            "2024-11-07T19:00", "2024-12-18T19:00",
            "2025-01-29T19:00", "2025-03-19T19:00",
            "2025-05-07T19:00", "2025-06-18T19:00", "2025-07-30T19:00",
            "2025-09-17T19:00", "2025-10-29T19:00", "2025-12-10T19:00",
            "2026-01-28T19:00", "2026-03-18T19:00",
        ],
    },
    # ---------- ECB: 8 meetings per year, decision at ~13:15 UTC ----------
    "ECB": {
        "utc_hour": 13,
        "pairs": ["EURUSD", "EURGBP", "EURJPY"],
        "releases": [
            "2022-02-03T13:15", "2022-03-10T13:15", "2022-04-14T13:15",
            "2022-06-09T13:15", "2022-07-21T13:15", "2022-09-08T13:15",
            "2022-10-27T13:15", "2022-12-15T13:15",
            "2023-02-02T13:15", "2023-03-16T13:15", "2023-05-04T13:15",
            "2023-06-15T13:15", "2023-07-27T13:15", "2023-09-14T13:15",
            "2023-10-26T13:15", "2023-12-14T13:15",
            "2024-01-25T13:15", "2024-03-07T13:15", "2024-04-11T13:15",
            "2024-06-06T13:15", "2024-07-18T13:15", "2024-09-12T13:15",
            "2024-10-17T13:15", "2024-12-12T13:15",
            "2025-01-30T13:15", "2025-03-06T13:15",
            "2025-04-17T13:15", "2025-06-05T13:15", "2025-07-24T13:15",
            "2025-09-11T13:15", "2025-10-30T13:15", "2025-12-11T13:15",
            "2026-01-29T13:15", "2026-03-05T13:15",
        ],
    },
    # ---------- BOE: 8 meetings per year, announcement at ~12:00 UTC ----------
    "BOE": {
        "utc_hour": 12,
        "pairs": ["GBPUSD", "EURGBP", "GBPJPY"],
        "releases": [
            "2022-02-03T12:00", "2022-03-17T12:00", "2022-05-05T12:00",
            "2022-06-16T12:00", "2022-08-04T12:00", "2022-09-22T12:00",
            "2022-11-03T12:00", "2022-12-15T12:00",
            "2023-02-02T12:00", "2023-03-23T12:00", "2023-05-11T12:00",
            "2023-06-22T12:00", "2023-08-03T12:00", "2023-09-21T12:00",
            "2023-11-02T12:00", "2023-12-14T12:00",
            "2024-02-01T12:00", "2024-03-21T12:00", "2024-05-09T12:00",
            "2024-06-20T12:00", "2024-08-01T12:00", "2024-09-19T12:00",
            "2024-11-07T12:00", "2024-12-19T12:00",
            "2025-02-06T12:00", "2025-03-20T12:00",
            "2025-05-08T12:00", "2025-06-19T12:00", "2025-08-07T12:00",
            "2025-09-18T12:00", "2025-11-06T12:00", "2025-12-18T12:00",
            "2026-02-05T12:00", "2026-03-19T12:00",
        ],
    },
    # ---------- PPI: variable mid-month at 13:30 UTC (BLS schedule) ----------
    "PPI": {
        "utc_hour": 13,
        "pairs": ["EURUSD", "USDJPY"],
        "releases": [
            "2022-01-13T13:30", "2022-02-15T13:30", "2022-03-15T13:30",
            "2022-04-13T13:30", "2022-05-12T13:30", "2022-06-14T13:30",
            "2022-07-14T13:30", "2022-08-11T13:30", "2022-09-14T13:30",
            "2022-10-12T13:30", "2022-11-15T13:30", "2022-12-09T13:30",
            "2023-01-18T13:30", "2023-02-16T13:30", "2023-03-15T13:30",
            "2023-04-13T13:30", "2023-05-11T13:30", "2023-06-14T13:30",
            "2023-07-13T13:30", "2023-08-11T13:30", "2023-09-14T13:30",
            "2023-10-11T13:30", "2023-11-15T13:30", "2023-12-08T13:30",
            "2024-01-12T13:30", "2024-02-16T13:30", "2024-03-14T13:30",
            "2024-04-11T13:30", "2024-05-14T13:30", "2024-06-13T13:30",
            "2024-07-12T13:30", "2024-08-13T13:30", "2024-09-12T13:30",
            "2024-10-11T13:30", "2024-11-14T13:30", "2024-12-12T13:30",
            "2025-01-14T13:30", "2025-02-13T13:30", "2025-03-13T13:30",
            "2025-04-11T13:30", "2025-05-15T13:30", "2025-06-12T13:30",
            "2025-07-15T13:30", "2025-08-14T13:30", "2025-09-11T13:30",
            "2025-10-14T13:30", "2025-11-13T13:30", "2025-12-11T13:30",
            "2026-01-15T13:30", "2026-02-12T13:30", "2026-03-12T13:30",
        ],
    },
    # ---------- RETAIL SALES: variable mid-month at 13:30 UTC ----------
    "RETAIL_SALES": {
        "utc_hour": 13,
        "pairs": ["EURUSD", "GBPUSD"],
        "releases": [
            "2022-01-14T13:30", "2022-02-16T13:30", "2022-03-16T13:30",
            "2022-04-14T13:30", "2022-05-17T13:30", "2022-06-15T13:30",
            "2022-07-15T13:30", "2022-08-17T13:30", "2022-09-15T13:30",
            "2022-10-14T13:30", "2022-11-16T13:30", "2022-12-15T13:30",
            "2023-01-18T13:30", "2023-02-15T13:30", "2023-03-15T13:30",
            "2023-04-14T13:30", "2023-05-16T13:30", "2023-06-15T13:30",
            "2023-07-18T13:30", "2023-08-15T13:30", "2023-09-15T13:30",
            "2023-10-17T13:30", "2023-11-15T13:30", "2023-12-14T13:30",
            "2024-01-17T13:30", "2024-02-15T13:30", "2024-03-14T13:30",
            "2024-04-15T13:30", "2024-05-15T13:30", "2024-06-18T13:30",
            "2024-07-16T13:30", "2024-08-15T13:30", "2024-09-17T13:30",
            "2024-10-17T13:30", "2024-11-15T13:30", "2024-12-17T13:30",
            "2025-01-16T13:30", "2025-02-14T13:30", "2025-03-17T13:30",
            "2025-04-16T13:30", "2025-05-15T13:30", "2025-06-17T13:30",
            "2025-07-16T13:30", "2025-08-15T13:30", "2025-09-17T13:30",
            "2025-10-17T13:30", "2025-11-14T13:30", "2025-12-16T13:30",
            "2026-01-15T13:30", "2026-02-18T13:30", "2026-03-17T13:30",
        ],
    },
}

# All 1h intraday — 5000 candles covers ~208 days (~7 months)
_FETCH_INTERVAL = "1h"
_FETCH_OUTPUTSIZE = 5000

PIP_SIZES = {
    "JPY": 0.01,
    "XAUUSD": 0.10,
    "default": 0.0001
}

SUPPORTED_EVENTS = list(EVENT_RELEASE_DATES.keys())

def parse_candle_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    # Twelve Data returns naive datetimes for forex (no TZ suffix).
    # Treat them as UTC so they compare correctly against our awareness-aware release dates.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

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

def parse_release_dt(s: str) -> datetime:
    """Parse a calendar entry like '2024-03-08T13:30' into a UTC-aware datetime."""
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def is_first_friday_of_month(dt: datetime) -> bool:
    if dt.weekday() != 4:  # 0=Monday, 4=Friday
        return False
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

    def identify_event_candles(
        self,
        candles: List[Dict[str, Any]],
        release_dts: List[datetime],
        lookback_events: int,
    ) -> List[int]:
        """
        Match each real release datetime to the nearest 1h candle whose
        datetime is <= the release time (i.e. the candle that was open
        at the moment of the release).

        Returns a list of candle indices (oldest first), capped at
        lookback_events entries, covering only releases whose candle
        falls inside the fetched window.
        """
        # Build a lookup: candle datetime -> index
        candle_dts = [
            (parse_candle_datetime(c["datetime"]), i)
            for i, c in enumerate(candles)
        ]
        # candles are already sorted oldest->newest

        matched_indices = []
        for release_dt in sorted(release_dts):
            # Find the last candle whose datetime <= release_dt
            best_idx = None
            for c_dt, c_idx in candle_dts:
                if c_dt <= release_dt:
                    best_idx = c_idx
                else:
                    break  # candles sorted, no need to go further
            if best_idx is not None:
                matched_indices.append(best_idx)

        # Deduplicate (in case two releases landed on the same candle)
        seen = set()
        deduped = []
        for idx in matched_indices:
            if idx not in seen:
                seen.add(idx)
                deduped.append(idx)

        return deduped[-lookback_events:]

    def compute_event_stats(self, candles: List[Dict[str, Any]], event_indices: List[int], pip_size: float, window_h: int = 4) -> Dict[str, Any]:
        if len(event_indices) < 5:
            return {
                "error": "Insufficient data: fewer than 5 event instances found",
                "sample_size": len(event_indices)
            }

        # immediate_ranges  = high/low range of the release candle + 2h (the spike)
        # extended_ranges   = high/low range of release candle + window_h (full reaction)
        immediate_ranges = []
        extended_ranges = []
        breakouts = 0
        fakeouts = 0

        imm_window = 2   # 2 candles (2h) for immediate spike measurement
        ext_window = window_h  # default 4h for extended reaction

        for i in event_indices:
            # Need at least ext_window candles ahead
            if i + ext_window >= len(candles):
                continue

            # --- Immediate reaction: release candle + next 2 candles (0–2h) ---
            imm_end = min(i + imm_window + 1, len(candles))
            imm_high = max(float(candles[j]["high"]) for j in range(i, imm_end))
            imm_low  = min(float(candles[j]["low"])  for j in range(i, imm_end))
            immediate_ranges.append((imm_high - imm_low) / pip_size)

            # --- Extended reaction: release candle + next ext_window candles ---
            ext_end = min(i + ext_window + 1, len(candles))
            ext_high = max(float(candles[j]["high"]) for j in range(i, ext_end))
            ext_low  = min(float(candles[j]["low"])  for j in range(i, ext_end))
            extended_ranges.append((ext_high - ext_low) / pip_size)

            # Direction: close of the 2h candle vs open of the release candle
            imm_last = min(i + imm_window, len(candles) - 1)
            ext_last = min(i + ext_window, len(candles) - 1)
            imm_direction = 1 if float(candles[imm_last]["close"]) > float(candles[i]["open"]) else -1
            ext_direction = 1 if float(candles[ext_last]["close"]) > float(candles[i]["open"]) else -1

            if imm_direction == ext_direction:
                breakouts += 1
            else:
                fakeouts += 1

        # Rename for clarity in aggregation (keep old variable names for compat)
        h1_ranges = immediate_ranges
        h4_ranges = extended_ranges

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

        if event not in EVENT_RELEASE_DATES:
            return {"error": f"Unsupported event: {event}"}

        if lookback_events > 48:
            lookback_events = 48

        try:
            event_info = EVENT_RELEASE_DATES[event]
            release_dts = [parse_release_dt(s) for s in event_info["releases"]]

            # All events now use 1h candles for accurate event-window measurement
            candles = await self.fetch_candles(
                pair,
                interval=_FETCH_INTERVAL,
                outputsize=_FETCH_OUTPUTSIZE,
            )

            event_indices = self.identify_event_candles(
                candles,
                release_dts,
                lookback_events,
            )

            if len(event_indices) < 5:
                return {
                    "error": (
                        f"Insufficient event occurrences found ({len(event_indices)}) in "
                        f"the available 1h candle window. "
                        f"Reduce lookback_events or try again later."
                    )
                }

            pip_size = get_pip_size(pair)
            stats = self.compute_event_stats(candles, event_indices, pip_size)

            if "error" in stats:
                return stats

            session_bias = get_session_bias(event_info["utc_hour"])

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

    async def volatility_regime_scan(self, pairs: List[str], event: str, lookback_events: int = 24) -> List[Dict[str, Any]]:
        results = []
        for pair in pairs:
            projection = await self.event_volatility_projection(pair, event, lookback_events)
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
        now_utc = datetime.now(timezone.utc)
        events_out = []
        for event, info in EVENT_RELEASE_DATES.items():
            # Find next upcoming release
            future = [
                s for s in info["releases"]
                if parse_release_dt(s) > now_utc
            ]
            next_release = min(future, default=None)
            events_out.append({
                "name": event,
                "utc_hour": info["utc_hour"],
                "primary_pairs": info.get("pairs", []),
                "next_release_utc": next_release,
                "total_releases_in_calendar": len(info["releases"]),
            })
        return {"events": events_out}


class AlreadySentResponse(Response):
    """No-op response for handlers where the transport already wrote to send()."""

    async def __call__(self, scope, receive, send) -> None:
        return

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
                "required": [
                    "pair", "event", "session_bias", "sample_size",
                    "expected_deviation_pips", "mean_deviation_pips",
                    "p75_deviation_pips", "h4_range_median_pips",
                    "breakout_probability", "mean_reversion_probability",
                    "fakeout_likelihood_score", "volatility_regime",
                    "confidence_score", "analysis_timestamp"
                ],
                "properties": {
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
                    "analysis_timestamp": {"type": "string"},
                    "error": {"type": "string"}
                }
            }
        ),
        Tool(
            name="volatility_regime_scan",
            description=(
                "Scans multiple FX pairs and returns their current volatility regime "
                "classification (Compressed / Normal / Expansionary) with recent pip "
                "range stats for a given macro event."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pairs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of FX pairs to scan e.g. ['EURUSD','GBPUSD','USDJPY']",
                        "examples": [["EURUSD", "GBPUSD", "USDJPY"]]
                    },
                    "event": {
                        "type": "string",
                        "description": "Event context for the scan e.g. NFP, CPI, FOMC",
                        "default": "NFP",
                        "examples": ["NFP", "CPI", "FOMC"]
                    }
                },
                "required": ["pairs"]
            },
            outputSchema={
                "type": "object",
                "required": ["event_context", "results", "timestamp"],
                "properties": {
                    "event_context": {
                        "type": "string",
                        "description": "The macro event used for the scan"
                    },
                    "results": {
                        "type": "array",
                        "description": "Array of volatility regime results per pair",
                        "items": {
                            "type": "object",
                            "properties": {
                                "pair": {"type": "string"},
                                "regime": {
                                    "type": "string",
                                    "description": "Compressed | Normal | Expansionary"
                                },
                                "median_dev_pips": {"type": "number"},
                                "confidence": {"type": "number"},
                                "error": {"type": "string"}
                            }
                        }
                    },
                    "timestamp": {"type": "string"}
                }
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
            event = arguments.get("event", "NFP")
            result = await eventvol.volatility_regime_scan(pairs, event)
            return {
                "event_context": event,
                "results": result,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

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


@asynccontextmanager
async def lifespan(app: Starlette):
    keepalive_task = asyncio.create_task(keepalive())
    try:
        yield
    finally:
        keepalive_task.cancel()
        try:
            await keepalive_task
        except asyncio.CancelledError:
            pass


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
    """
    Handle MCP JSON-RPC messages.
    Enforces Context Protocol JWT auth on tools/call only.
    Discovery methods (tools/list, initialize) remain open.
    Body is replayed so the SSE transport can still read the payload.
    """
    # Read body once
    body_bytes = await request.body()

    # Parse the JSON-RPC method name
    try:
        body_json = json.loads(body_bytes)
        method = body_json.get("method", "")
    except Exception:
        body_json = {}
        method = ""

    # Only enforce auth on protected methods (tools/call)
    # is_protected_mcp_method returns True for tools/call, False for everything else
    if is_protected_mcp_method(method):
        try:
            await verify_context_request(
                authorization_header=request.headers.get("authorization", "")
            )
        except ContextError as e:
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32001,
                        "message": f"Unauthorized: {e.message}"
                    },
                    "id": body_json.get("id")
                },
                status_code=401
            )

    # Replay the body so the SSE transport can read it
    # (we already consumed request.body() above, so we must reconstruct receive)
    async def receive():
        return {
            "type": "http.request",
            "body": body_bytes,
            "more_body": False
        }

    # Pass to MCP SSE transport
    await sse_transport.handle_post_message(
        request.scope,
        receive,        # reconstructed receive — NOT request.receive
        request._send
    )
    return AlreadySentResponse()


app = Starlette(
    routes=[
        Route("/", handle_root),
        Route("/health", handle_health),
        Route("/sse", handle_sse),
        Route("/messages", handle_messages, methods=["POST"]),
    ],
    lifespan=lifespan,
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
