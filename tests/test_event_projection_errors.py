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

from server import EventVolServer


def run(coro):
    return asyncio.run(coro)


def test_event_projection_error_includes_pair_and_event(monkeypatch):
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    server = EventVolServer()

    async def fake_dates(event: str, lookback_months: int = 24):
        return []

    monkeypatch.setattr("server.fetch_event_dates_from_finnhub", fake_dates)
    monkeypatch.setattr("server.HARDCODED_EVENT_DATES", {})

    result = run(server.event_volatility_projection("EUR/USD", "RETAIL_SALES", 12))

    assert result["pair"] == "EURUSD"
    assert result["event"] == "RETAIL_SALES"
    assert result["success"] is False
    assert "error" in result


def test_unsupported_event_includes_pair_and_event(monkeypatch):
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    server = EventVolServer()

    result = run(server.event_volatility_projection("GBP/USD", "PMI", 12))

    assert result == {
        "pair": "GBPUSD",
        "event": "PMI",
        "success": False,
        "error": "Event 'PMI' not supported. Use: ['NFP', 'CPI', 'FOMC', 'ECB', 'BOE', 'PPI', 'RETAIL_SALES']",
    }
