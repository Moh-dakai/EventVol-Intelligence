import asyncio
import os
import sys
import types

# Stub ctxprotocol so server.py imports cleanly in local tests.
_ctx = types.ModuleType("ctxprotocol")
_ctx.ContextError = type("ContextError", (Exception,), {"message": ""})
_ctx.is_protected_mcp_method = lambda m: False
_ctx.verify_context_request = lambda **kw: None
sys.modules.setdefault("ctxprotocol", _ctx)

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import server
from server import EventVolServer


def run(coro):
    return asyncio.run(coro)


def make_candles(count: int = 20):
    candles = []
    for i in range(count):
        base = 1.1000 + (i * 0.0010)
        candles.append(
            {
                "datetime": f"2025-01-{(i // 6) + 1:02d} {(i % 24):02d}:00:00",
                "open": f"{base:.4f}",
                "high": f"{base + 0.0020:.4f}",
                "low": f"{base - 0.0010:.4f}",
                "close": f"{base + 0.0015:.4f}",
            }
        )
    return candles


def test_event_projection_error_includes_pair_event_and_data_available(monkeypatch):
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    server._EVENT_DATE_CACHE.clear()
    eventvol = EventVolServer()

    async def fake_dates(event: str, lookback_months: int = 24):
        return []

    monkeypatch.setattr("server.fetch_event_dates_from_finnhub", fake_dates)
    monkeypatch.setattr("server.HARDCODED_EVENT_DATES", {})

    result = run(eventvol.event_volatility_projection("EUR/USD", "RETAIL_SALES", 12))

    assert result["pair"] == "EURUSD"
    assert result["event"] == "RETAIL_SALES"
    assert result["success"] is False
    assert result["dataAvailable"] is False
    assert "error" in result


def test_unsupported_event_includes_pair_event_and_data_available(monkeypatch):
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    eventvol = EventVolServer()

    result = run(eventvol.event_volatility_projection("GBP/USD", "PMI", 12))

    assert result == {
        "pair": "GBPUSD",
        "event": "PMI",
        "success": False,
        "dataAvailable": False,
        "error": "Event 'PMI' not supported. Use: ['NFP', 'CPI', 'FOMC', 'ECB', 'BOE', 'PPI', 'RETAIL_SALES']",
    }


def test_low_sample_three_matches_returns_success(monkeypatch):
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    eventvol = EventVolServer()
    candles = make_candles()
    event_dates = [
        server.datetime(2025, 1, 1, 13, 30),
        server.datetime(2024, 12, 1, 13, 30),
        server.datetime(2024, 11, 1, 13, 30),
    ]
    indices = iter([0, 5, 10])

    async def fake_dates(event: str, lookback_months: int = 24):
        return event_dates

    async def fake_fetch_candles(pair: str, interval: str = "1day", outputsize: int = 500):
        return candles

    monkeypatch.setattr("server.fetch_event_dates_from_finnhub", fake_dates)
    monkeypatch.setattr("server.HARDCODED_EVENT_DATES", {})
    monkeypatch.setattr(eventvol, "fetch_candles", fake_fetch_candles)
    monkeypatch.setattr("server.find_candle_index_for_event", lambda candles, event_dt: next(indices))

    result = run(eventvol.event_volatility_projection("EURUSD", "RETAIL_SALES", 12))

    assert result["success"] is True
    assert result["dataAvailable"] is True
    assert result["low_sample_warning"] is True
    assert result["sample_size"] == 3
    assert len(result["event_dates_used"]) == 3


def test_fetch_candles_uses_in_memory_cache(monkeypatch):
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    server._CANDLE_CACHE.clear()
    eventvol = EventVolServer()
    call_count = {"get": 0}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"values": make_candles(6)}

    class FakeAsyncClient:
        def __init__(self, timeout: float):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None):
            call_count["get"] += 1
            return FakeResponse()

    monkeypatch.setattr("server.httpx.AsyncClient", FakeAsyncClient)

    first = run(eventvol.fetch_candles("EURUSD", interval="1h", outputsize=5000))
    second = run(eventvol.fetch_candles("EURUSD", interval="1h", outputsize=5000))

    assert call_count["get"] == 1
    assert first == second
