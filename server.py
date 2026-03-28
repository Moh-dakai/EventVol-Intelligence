import asyncio
import json
import os
import statistics
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
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

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
FINNHUB_EVENT_MAP = {
    "NFP": "Nonfarm Payrolls",
    "CPI": "Consumer Price Index",
    "FOMC": "Fed Interest Rate Decision",
    "ECB": "ECB Interest Rate Decision",
    "BOE": "BoE Interest Rate Decision",
    "PPI": "Producer Price Index",
    "RETAIL_SALES": "Retail Sales",
}

# -----------------------------------------------------------------
# Economic Calendar  — real historical UTC release datetimes
# Format: "YYYY-MM-DDTHH:MM"  (UTC, no seconds needed)
# Sources: BLS.gov release calendar, Federal Reserve, ECB, BOE
# -----------------------------------------------------------------
HARDCODED_EVENT_DATES: dict[str, list[datetime]] = {
    "NFP": [
        datetime(2022, 1, 7, 13, 30), datetime(2022, 2, 4, 13, 30),
        datetime(2022, 3, 4, 13, 30), datetime(2022, 4, 1, 13, 30),
        datetime(2022, 5, 6, 13, 30), datetime(2022, 6, 3, 13, 30),
        datetime(2022, 7, 8, 13, 30), datetime(2022, 8, 5, 13, 30),
        datetime(2022, 9, 2, 13, 30), datetime(2022, 10, 7, 13, 30),
        datetime(2022, 11, 4, 13, 30), datetime(2022, 12, 2, 13, 30),
        datetime(2023, 1, 6, 13, 30), datetime(2023, 2, 3, 13, 30),
        datetime(2023, 3, 10, 13, 30), datetime(2023, 4, 7, 13, 30),
        datetime(2023, 5, 5, 13, 30), datetime(2023, 6, 2, 13, 30),
        datetime(2023, 7, 7, 13, 30), datetime(2023, 8, 4, 13, 30),
        datetime(2023, 9, 1, 13, 30), datetime(2023, 10, 6, 13, 30),
        datetime(2023, 11, 3, 13, 30), datetime(2023, 12, 8, 13, 30),
        datetime(2024, 1, 5, 13, 30), datetime(2024, 2, 2, 13, 30),
        datetime(2024, 3, 8, 13, 30), datetime(2024, 4, 5, 13, 30),
        datetime(2024, 5, 3, 13, 30), datetime(2024, 6, 7, 13, 30),
        datetime(2024, 7, 5, 13, 30), datetime(2024, 8, 2, 13, 30),
        datetime(2024, 9, 6, 13, 30), datetime(2024, 10, 4, 13, 30),
        datetime(2024, 11, 1, 13, 30), datetime(2024, 12, 6, 13, 30),
        datetime(2025, 1, 10, 13, 30), datetime(2025, 2, 7, 13, 30),
        datetime(2025, 3, 7, 13, 30), datetime(2025, 4, 4, 13, 30),
        datetime(2025, 5, 2, 13, 30), datetime(2025, 6, 6, 13, 30),
        datetime(2025, 7, 11, 13, 30), datetime(2025, 8, 1, 13, 30),
        datetime(2025, 9, 5, 13, 30), datetime(2025, 10, 3, 13, 30),
        datetime(2025, 11, 7, 13, 30), datetime(2025, 12, 5, 13, 30),
    ],
    "CPI": [
        datetime(2022, 1, 12, 13, 30), datetime(2022, 2, 10, 13, 30),
        datetime(2022, 3, 10, 13, 30), datetime(2022, 4, 12, 13, 30),
        datetime(2022, 5, 11, 13, 30), datetime(2022, 6, 10, 13, 30),
        datetime(2022, 7, 13, 13, 30), datetime(2022, 8, 10, 13, 30),
        datetime(2022, 9, 13, 13, 30), datetime(2022, 10, 13, 13, 30),
        datetime(2022, 11, 10, 13, 30), datetime(2022, 12, 13, 13, 30),
        datetime(2023, 1, 12, 13, 30), datetime(2023, 2, 14, 13, 30),
        datetime(2023, 3, 14, 13, 30), datetime(2023, 4, 12, 13, 30),
        datetime(2023, 5, 10, 13, 30), datetime(2023, 6, 13, 13, 30),
        datetime(2023, 7, 12, 13, 30), datetime(2023, 8, 10, 13, 30),
        datetime(2023, 9, 13, 13, 30), datetime(2023, 10, 12, 13, 30),
        datetime(2023, 11, 14, 13, 30), datetime(2023, 12, 12, 13, 30),
        datetime(2024, 1, 11, 13, 30), datetime(2024, 2, 13, 13, 30),
        datetime(2024, 3, 12, 13, 30), datetime(2024, 4, 10, 13, 30),
        datetime(2024, 5, 15, 13, 30), datetime(2024, 6, 12, 13, 30),
        datetime(2024, 7, 11, 13, 30), datetime(2024, 8, 14, 13, 30),
        datetime(2024, 9, 11, 13, 30), datetime(2024, 10, 10, 13, 30),
        datetime(2024, 11, 13, 13, 30), datetime(2024, 12, 11, 13, 30),
        datetime(2025, 1, 15, 13, 30), datetime(2025, 2, 12, 13, 30),
        datetime(2025, 3, 12, 13, 30), datetime(2025, 4, 9, 13, 30),
        datetime(2025, 5, 13, 13, 30), datetime(2025, 6, 11, 13, 30),
        datetime(2025, 7, 15, 13, 30), datetime(2025, 8, 12, 13, 30),
        datetime(2025, 9, 10, 13, 30), datetime(2025, 11, 13, 13, 30),
        datetime(2025, 12, 10, 13, 30),
    ],
    "FOMC": [
        datetime(2022, 3, 16, 19, 0), datetime(2022, 5, 4, 19, 0),
        datetime(2022, 6, 15, 19, 0), datetime(2022, 7, 27, 19, 0),
        datetime(2022, 9, 21, 19, 0), datetime(2022, 11, 2, 19, 0),
        datetime(2022, 12, 14, 19, 0),
        datetime(2023, 2, 1, 19, 0), datetime(2023, 3, 22, 19, 0),
        datetime(2023, 5, 3, 19, 0), datetime(2023, 6, 14, 19, 0),
        datetime(2023, 7, 26, 19, 0), datetime(2023, 9, 20, 19, 0),
        datetime(2023, 11, 1, 19, 0), datetime(2023, 12, 13, 19, 0),
        datetime(2024, 1, 31, 19, 0), datetime(2024, 3, 20, 19, 0),
        datetime(2024, 5, 1, 19, 0), datetime(2024, 6, 12, 19, 0),
        datetime(2024, 7, 31, 19, 0), datetime(2024, 9, 18, 19, 0),
        datetime(2024, 11, 7, 19, 0), datetime(2024, 12, 18, 19, 0),
        datetime(2025, 1, 29, 19, 0), datetime(2025, 3, 19, 19, 0),
        datetime(2025, 5, 7, 19, 0), datetime(2025, 6, 18, 19, 0),
        datetime(2025, 7, 30, 19, 0), datetime(2025, 9, 17, 19, 0),
        datetime(2025, 11, 7, 19, 0), datetime(2025, 12, 10, 19, 0),
        datetime(2026, 1, 29, 19, 0), datetime(2026, 3, 18, 19, 0),
    ],
    "ECB": [
        datetime(2022, 2, 3, 13, 15), datetime(2022, 3, 10, 13, 15),
        datetime(2022, 4, 14, 13, 15), datetime(2022, 6, 9, 13, 15),
        datetime(2022, 7, 21, 13, 15), datetime(2022, 9, 8, 13, 15),
        datetime(2022, 10, 27, 13, 15), datetime(2022, 12, 15, 13, 15),
        datetime(2023, 2, 2, 13, 15), datetime(2023, 3, 16, 13, 15),
        datetime(2023, 5, 4, 13, 15), datetime(2023, 6, 15, 13, 15),
        datetime(2023, 7, 27, 13, 15), datetime(2023, 9, 14, 13, 15),
        datetime(2023, 10, 26, 13, 15), datetime(2023, 12, 14, 13, 15),
        datetime(2024, 1, 25, 13, 15), datetime(2024, 3, 7, 13, 15),
        datetime(2024, 4, 11, 13, 15), datetime(2024, 6, 6, 13, 15),
        datetime(2024, 7, 18, 13, 15), datetime(2024, 9, 12, 13, 15),
        datetime(2024, 10, 17, 13, 15), datetime(2024, 12, 12, 13, 15),
        datetime(2025, 1, 30, 13, 15), datetime(2025, 3, 6, 13, 15),
        datetime(2025, 4, 17, 13, 15), datetime(2025, 6, 5, 13, 15),
        datetime(2025, 7, 24, 13, 15), datetime(2025, 9, 11, 13, 15),
        datetime(2025, 10, 30, 13, 15), datetime(2025, 12, 18, 13, 15),
    ],
    "BOE": [
        datetime(2022, 2, 3, 12, 0), datetime(2022, 3, 17, 12, 0),
        datetime(2022, 5, 5, 12, 0), datetime(2022, 6, 16, 12, 0),
        datetime(2022, 8, 4, 12, 0), datetime(2022, 9, 22, 12, 0),
        datetime(2022, 11, 3, 12, 0), datetime(2022, 12, 15, 12, 0),
        datetime(2023, 2, 2, 12, 0), datetime(2023, 3, 23, 12, 0),
        datetime(2023, 5, 11, 12, 0), datetime(2023, 6, 22, 12, 0),
        datetime(2023, 8, 3, 12, 0), datetime(2023, 9, 21, 12, 0),
        datetime(2023, 11, 2, 12, 0), datetime(2023, 12, 14, 12, 0),
        datetime(2024, 2, 1, 12, 0), datetime(2024, 3, 21, 12, 0),
        datetime(2024, 5, 9, 12, 0), datetime(2024, 6, 20, 12, 0),
        datetime(2024, 8, 1, 12, 0), datetime(2024, 9, 19, 12, 0),
        datetime(2024, 11, 7, 12, 0), datetime(2024, 12, 19, 12, 0),
        datetime(2025, 2, 6, 12, 0), datetime(2025, 3, 20, 12, 0),
        datetime(2025, 5, 8, 12, 0), datetime(2025, 6, 19, 12, 0),
        datetime(2025, 8, 7, 12, 0), datetime(2025, 9, 18, 12, 0),
        datetime(2025, 11, 6, 12, 0), datetime(2025, 12, 18, 12, 0),
    ],
    "PPI": [
        datetime(2022, 1, 13, 13, 30), datetime(2022, 2, 15, 13, 30),
        datetime(2022, 3, 15, 13, 30), datetime(2022, 4, 13, 13, 30),
        datetime(2022, 5, 12, 13, 30), datetime(2022, 6, 14, 13, 30),
        datetime(2022, 7, 14, 13, 30), datetime(2022, 8, 11, 13, 30),
        datetime(2022, 9, 14, 13, 30), datetime(2022, 10, 14, 13, 30),
        datetime(2022, 11, 15, 13, 30), datetime(2022, 12, 14, 13, 30),
        datetime(2023, 1, 18, 13, 30), datetime(2023, 2, 16, 13, 30),
        datetime(2023, 3, 15, 13, 30), datetime(2023, 4, 13, 13, 30),
        datetime(2023, 5, 11, 13, 30), datetime(2023, 6, 14, 13, 30),
        datetime(2023, 7, 13, 13, 30), datetime(2023, 8, 11, 13, 30),
        datetime(2023, 9, 14, 13, 30), datetime(2023, 10, 11, 13, 30),
        datetime(2023, 11, 15, 13, 30), datetime(2023, 12, 14, 13, 30),
        datetime(2024, 1, 12, 13, 30), datetime(2024, 2, 16, 13, 30),
        datetime(2024, 3, 14, 13, 30), datetime(2024, 4, 11, 13, 30),
        datetime(2024, 5, 14, 13, 30), datetime(2024, 6, 13, 13, 30),
        datetime(2024, 7, 12, 13, 30), datetime(2024, 8, 13, 13, 30),
        datetime(2024, 9, 12, 13, 30), datetime(2024, 10, 11, 13, 30),
        datetime(2024, 11, 14, 13, 30), datetime(2024, 12, 12, 13, 30),
        datetime(2025, 1, 14, 13, 30), datetime(2025, 2, 13, 13, 30),
        datetime(2025, 3, 13, 13, 30), datetime(2025, 4, 11, 13, 30),
        datetime(2025, 5, 15, 13, 30), datetime(2025, 6, 12, 13, 30),
        datetime(2025, 7, 15, 13, 30), datetime(2025, 8, 14, 13, 30),
        datetime(2025, 9, 11, 13, 30), datetime(2025, 12, 11, 13, 30),
    ],
    "RETAIL_SALES": [
        datetime(2022, 1, 14, 13, 30), datetime(2022, 2, 16, 13, 30),
        datetime(2022, 3, 16, 13, 30), datetime(2022, 4, 14, 13, 30),
        datetime(2022, 5, 17, 13, 30), datetime(2022, 6, 15, 13, 30),
        datetime(2022, 7, 15, 13, 30), datetime(2022, 8, 17, 13, 30),
        datetime(2022, 9, 15, 13, 30), datetime(2022, 10, 14, 13, 30),
        datetime(2022, 11, 16, 13, 30), datetime(2022, 12, 15, 13, 30),
        datetime(2023, 1, 18, 13, 30), datetime(2023, 2, 15, 13, 30),
        datetime(2023, 3, 15, 13, 30), datetime(2023, 4, 14, 13, 30),
        datetime(2023, 5, 16, 13, 30), datetime(2023, 6, 15, 13, 30),
        datetime(2023, 7, 18, 13, 30), datetime(2023, 8, 15, 13, 30),
        datetime(2023, 9, 15, 13, 30), datetime(2023, 10, 17, 13, 30),
        datetime(2023, 11, 15, 13, 30), datetime(2023, 12, 14, 13, 30),
        datetime(2024, 1, 17, 13, 30), datetime(2024, 2, 15, 13, 30),
        datetime(2024, 3, 15, 13, 30), datetime(2024, 4, 15, 13, 30),
        datetime(2024, 5, 15, 13, 30), datetime(2024, 6, 18, 13, 30),
        datetime(2024, 7, 16, 13, 30), datetime(2024, 8, 15, 13, 30),
        datetime(2024, 9, 17, 13, 30), datetime(2024, 10, 17, 13, 30),
        datetime(2024, 11, 15, 13, 30), datetime(2024, 12, 17, 13, 30),
        datetime(2025, 1, 16, 13, 30), datetime(2025, 2, 14, 13, 30),
        datetime(2025, 3, 17, 13, 30), datetime(2025, 4, 16, 13, 30),
        datetime(2025, 5, 15, 13, 30), datetime(2025, 6, 17, 13, 30),
        datetime(2025, 7, 17, 13, 30), datetime(2025, 8, 15, 13, 30),
        datetime(2025, 9, 17, 13, 30), datetime(2025, 12, 16, 13, 30),
    ],
}

# All 1h intraday — 5000 candles covers ~208 days (~7 months)
_FETCH_INTERVAL = "1h"
_FETCH_OUTPUTSIZE = 5000

PIP_SIZES = {
    "JPY": 0.01,
    "XAUUSD": 0.10,
    "default": 0.0001
}

SUPPORTED_EVENTS = list(HARDCODED_EVENT_DATES.keys())

def parse_candle_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "")
    if "T" in normalized:
        return datetime.strptime(normalized[:16], "%Y-%m-%dT%H:%M")
    return datetime.strptime(normalized[:16], "%Y-%m-%d %H:%M")

def get_pip_size(pair: str) -> float:
    if "JPY" in pair:
        return PIP_SIZES["JPY"]
    elif pair == "XAUUSD":
        return PIP_SIZES["XAUUSD"]
    else:
        return PIP_SIZES["default"]

SESSIONS = {
    "Asia": (0, 8),
    "London": (8, 13),
    "NY": (13, 21),
    "Overlap": (12, 16),
}


def classify_session(utc_hour: int) -> str:
    for session, (start, end) in SESSIONS.items():
        if start <= utc_hour < end:
            return session
    return "Off-Hours"


def find_candle_index_for_event(candles: list[dict], event_dt: datetime) -> int | None:
    """
    Find the 1H candle index that matches a real event datetime.
    Matches on date + hour. Returns None if no match found.
    Candles from Twelve Data are in format: "2024-01-12 13:00:00"
    """
    target_date = event_dt.strftime("%Y-%m-%d")
    target_hour = event_dt.hour

    for i, candle in enumerate(candles):
        try:
            candle_str = candle["datetime"]
            candle_dt = (
                datetime.strptime(candle_str[:16], "%Y-%m-%d %H:%M")
                if " " in candle_str
                else datetime.strptime(candle_str[:16], "%Y-%m-%dT%H:%M")
            )
        except Exception:
            continue

        if candle_dt.strftime("%Y-%m-%d") == target_date and candle_dt.hour == target_hour:
            return i

    return None


async def fetch_event_dates_from_finnhub(event: str, lookback_months: int = 24) -> list[datetime]:
    """
    Fetch real historical event release dates from Finnhub Economic Calendar.
    Returns list of datetimes sorted most-recent-first.
    """
    keyword = FINNHUB_EVENT_MAP.get(event.upper())
    if not keyword or not FINNHUB_API_KEY:
        return []

    all_dates: list[datetime] = []
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=lookback_months * 30)

    chunk_end = end_date
    while chunk_end > start_date:
        chunk_start = max(chunk_end - timedelta(days=180), start_date)
        params = {
            "from": chunk_start.strftime("%Y-%m-%d"),
            "to": chunk_end.strftime("%Y-%m-%d"),
            "token": FINNHUB_API_KEY,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{FINNHUB_BASE_URL}/calendar/economic",
                    params=params,
                )
                response.raise_for_status()
                data = response.json()
        except Exception:
            chunk_end = chunk_start
            continue

        for calendar_event in data.get("economicCalendar", []):
            event_name = calendar_event.get("event", "")
            if keyword.lower() not in event_name.lower():
                continue

            country = calendar_event.get("country", "").upper()
            if country not in ("US", "USA", "UNITED STATES", "EU", "GB", "UK"):
                continue

            time_str = calendar_event.get("time", "")
            if not time_str:
                continue

            try:
                parsed = datetime.strptime(
                    time_str[:16].replace("T", " "),
                    "%Y-%m-%d %H:%M",
                )
                all_dates.append(parsed)
            except Exception:
                continue

        chunk_end = chunk_start

    seen_dates = set()
    unique_dates = []
    for event_dt in sorted(all_dates, reverse=True):
        date_key = event_dt.strftime("%Y-%m-%d")
        if date_key in seen_dates:
            continue
        seen_dates.add(date_key)
        unique_dates.append(event_dt)

    return unique_dates

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

        lookback_events = min(int(lookback_events), 48)

        if event not in FINNHUB_EVENT_MAP:
            return {
                "pair": pair,
                "event": event,
                "success": False,
                "error": f"Event '{event}' not supported. Use: {list(FINNHUB_EVENT_MAP.keys())}",
            }

        try:
            event_dates = await fetch_event_dates_from_finnhub(event, lookback_months=24)
            if len(event_dates) < 5 and event in HARDCODED_EVENT_DATES:
                event_dates = sorted(HARDCODED_EVENT_DATES[event], reverse=True)

            event_dates = event_dates[:lookback_events]

            if len(event_dates) < 5:
                return {
                    "pair": pair,
                    "event": event,
                    "success": False,
                    "error": (
                        f"Insufficient event dates found ({len(event_dates)}). "
                        "Check FINNHUB_API_KEY is set in Railway environment variables."
                    ),
                }

            candles = await self.fetch_candles(
                pair,
                interval=_FETCH_INTERVAL,
                outputsize=_FETCH_OUTPUTSIZE,
            )

            pip_size = get_pip_size(pair)

            event_indices = []
            matched_dates = []
            for event_dt in event_dates:
                idx = find_candle_index_for_event(candles, event_dt)
                if idx is not None and idx + 4 < len(candles):
                    event_indices.append(idx)
                    matched_dates.append(event_dt.strftime("%Y-%m-%d"))

            if len(event_indices) < 5:
                return {
                    "pair": pair,
                    "event": event,
                    "success": False,
                    "error": (
                        f"Only {len(event_indices)} event dates matched candle data (need 5+). "
                        f"Dates found: {[d.strftime('%Y-%m-%d') for d in event_dates[:5]]}. "
                        f"Try EURUSD, GBPUSD, or USDJPY for best coverage."
                    ),
                }

            stats = self.compute_event_stats(candles, event_indices, pip_size)
            if "error" in stats:
                return {
                    "pair": pair,
                    "event": event,
                    "success": False,
                    **stats,
                }

            return {
                "pair": pair,
                "event": event,
                "success": True,
                "session_bias": classify_session(event_dates[0].hour),
                "data_source": "Finnhub economic calendar + Twelve Data 1H candles",
                "event_dates_used": matched_dates,
                **stats,
                "analysis_timestamp": datetime.utcnow().isoformat() + "Z",
            }

        except ValueError as e:
            return {
                "pair": pair,
                "event": event,
                "success": False,
                "error": str(e),
            }
        except Exception as e:
            return {
                "pair": pair,
                "event": event,
                "success": False,
                "error": f"Unexpected error: {str(e)}",
            }

    async def volatility_regime_scan(self, pairs: List[str], event: str, lookback_events: int = 24) -> List[Dict[str, Any]]:
        event = event.upper()
        results = []

        if event not in HARDCODED_EVENT_DATES:
            return [{"error": f"Unsupported event: {event}"}]

        event_dates = sorted(HARDCODED_EVENT_DATES[event], reverse=True)[:20]

        for pair in pairs:
            normalized_pair = pair.upper().replace("/", "")
            try:
                candles = await self.fetch_candles(
                    normalized_pair,
                    interval=_FETCH_INTERVAL,
                    outputsize=_FETCH_OUTPUTSIZE,
                )
                pip_size = get_pip_size(normalized_pair)

                event_indices = []
                for event_dt in event_dates:
                    idx = find_candle_index_for_event(candles, event_dt)
                    if idx is not None and idx + 4 < len(candles):
                        event_indices.append(idx)

                if len(event_indices) >= 5:
                    stats = self.compute_event_stats(candles, event_indices, pip_size)
                    results.append({
                        "pair": normalized_pair,
                        "regime": stats["volatility_regime"],
                        "median_dev_pips": stats["expected_deviation_pips"],
                        "confidence": stats["confidence_score"],
                    })
                else:
                    results.append({
                        "pair": normalized_pair,
                        "regime": "Insufficient Data",
                        "matched_events": len(event_indices),
                    })
            except Exception as e:
                results.append({"pair": normalized_pair, "error": str(e)})

        return results

    def list_supported_events(self) -> Dict[str, Any]:
        return {
            "supported_events": {
                event: {
                    "total_dates_available": len(dates),
                    "earliest": min(dates).strftime("%Y-%m-%d"),
                    "latest": max(dates).strftime("%Y-%m-%d"),
                    "utc_hour": dates[0].hour,
                }
                for event, dates in HARDCODED_EVENT_DATES.items()
            }
        }


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
                "required": ["pair", "event"],
                "properties": {
                    "pair": {"type": "string"},
                    "event": {"type": "string"},
                    "success": {"type": "boolean"},
                    "error": {"type": "string"},
                    "session_bias": {"type": "string"},
                    "sample_size": {"type": "integer"},
                    "event_dates_used": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
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
                    "data_source": {"type": "string"}
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
                    "supported_events": {
                        "type": "object"
                    }
                },
                "required": ["supported_events"]
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
            lookback_events = arguments.get("lookback_events", 24)
            result = await eventvol.volatility_regime_scan(pairs, event, lookback_events)
            return {
                "event_context": event,
                "results": result,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        if name == "list_supported_events":
            return eventvol.list_supported_events()

        return {"error": f"Unknown tool: {name}"}
    except Exception as exc:
        if name == "event_volatility_projection":
            return {
                "pair": str(arguments.get("pair", "")).upper().replace("/", ""),
                "event": str(arguments.get("event", "")).upper(),
                "success": False,
                "error": f"Internal server error: {str(exc)}",
                "analysis_timestamp": datetime.utcnow().isoformat() + "Z",
            }

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
