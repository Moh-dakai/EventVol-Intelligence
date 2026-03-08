#!/usr/bin/env python3
"""
Test script for EventVol Intelligence MCP Server
Run this to test the core functionality locally.
"""

import asyncio
import json
from server import EventVolServer

async def test_server():
    print("🧪 Testing EventVol Intelligence Server")
    print("=" * 50)

    server = EventVolServer()

    # Test 1: List supported events
    print("\n1. Testing list_supported_events:")
    events = server.list_supported_events()
    print(json.dumps(events, indent=2))

    # Test 2: Fetch candles (real API call)
    print("\n2. Testing fetch_candles for EURUSD:")
    try:
        candles = await server.fetch_candles("EURUSD")
        print(f"✅ Fetched {len(candles)} candles")
        if candles:
            print(f"   First candle: {candles[0]['datetime']}")
            print(f"   Last candle: {candles[-1]['datetime']}")
    except Exception as e:
        print(f"❌ Error: {e}")
        return

    # Test 3: Identify event candles
    print("\n3. Testing identify_event_candles for NFP:")
    indices = server.identify_event_candles(candles, "NFP", 24)
    print(f"   Found {len(indices)} NFP events at indices: {indices}")

    # Test 4: Full volatility projection
    if len(indices) >= 5:
        print("\n4. Testing full event_volatility_projection:")
        result = await server.event_volatility_projection("EURUSD", "NFP", 24)
        print(json.dumps(result, indent=2))
    else:
        print(f"\n4. Skipping full test: only {len(indices)} events found (need ≥5)")

    print("\n🎉 All tests completed!")

if __name__ == "__main__":
    asyncio.run(test_server())