"""
Sanity tests for event-specific analysis fixes.
Run from project root:
  python -m pytest tests/test_event_specificity.py -v
Requires TWELVE_DATA_API_KEY in .env
"""
import asyncio
import sys
import os
import types

# ---- stub ctxprotocol so we can import server.py without the marketplace SDK ----
_ctx = types.ModuleType("ctxprotocol")
_ctx.ContextError = type("ContextError", (Exception,), {"message": ""})
_ctx.is_protected_mcp_method = lambda m: False
_ctx.verify_context_request = lambda **kw: None
sys.modules.setdefault("ctxprotocol", _ctx)
# ---------------------------------------------------------------------------------

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

import pytest
from server import EventVolServer


@pytest.fixture(scope="module")
def server():
    return EventVolServer()


def run(coro):
    return asyncio.run(coro)


def test_cpi_vs_retail_sales_differ(server):
    """Blocker 1: CPI and Retail Sales must produce different pip deviations."""
    cpi = run(server.event_volatility_projection("EURUSD", "CPI", 12))
    rs  = run(server.event_volatility_projection("EURUSD", "RETAIL_SALES", 12))
    assert "error" not in cpi, f"CPI error: {cpi.get('error')}"
    assert "error" not in rs,  f"Retail Sales error: {rs.get('error')}"
    assert cpi["expected_deviation_pips"] != rs["expected_deviation_pips"], (
        f"CPI and Retail Sales returned identical pip deviations: "
        f"{cpi['expected_deviation_pips']} — event-specific analysis still broken."
    )


def test_gbpusd_nfp_magnitude(server):
    """Blocker 2: GBPUSD/NFP expected_deviation_pips should be 15–80 pips (not 100+)."""
    result = run(server.event_volatility_projection("GBPUSD", "NFP", 12))
    assert "error" not in result, f"NFP error: {result.get('error')}"
    pips = result["expected_deviation_pips"]
    assert 10 <= pips <= 80, (
        f"GBPUSD/NFP deviation {pips} pips is outside realistic range [10, 80]. "
        f"Still measuring daily ranges instead of event windows?"
    )


def test_sample_sizes_nonzero(server):
    """All events must return >=5 samples for at least one canonical pair."""
    for event, pair in [("NFP", "EURUSD"), ("CPI", "EURUSD"), ("FOMC", "EURUSD")]:
        result = run(server.event_volatility_projection(pair, event, 12))
        assert "error" not in result, f"{event} error: {result.get('error')}"
        assert result["sample_size"] >= 5, (
            f"{event}/{pair} only found {result['sample_size']} samples — need >=5."
        )
