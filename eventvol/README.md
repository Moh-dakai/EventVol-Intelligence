# EventVol Intelligence MCP Server

A Model Context Protocol (MCP) server that provides statistical analysis of FX volatility around macro economic events.

## Features

- Analyze expected price deviations for FX pairs during macro events (NFP, CPI, FOMC, etc.)
- Calculate breakout and fakeout probabilities
- Determine volatility regimes
- Support for multiple FX pairs and events

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up your Twelve Data API key in `.env`:
   ```
   TWELVE_DATA_API_KEY=your_actual_api_key
   ```

3. Run the server:
   ```bash
   python server.py
   ```

4. Configure Claude Desktop by adding the server to your `claude_desktop_config.json`.

## Usage

Once integrated with Claude Desktop, you can ask questions like:
- "What is the expected volatility for GBPUSD during NFP?"
- "Scan volatility regimes for EURUSD, GBPUSD, USDJPY on CPI"

## Tools

- `event_volatility_projection`: Core analysis for a single pair and event
- `volatility_regime_scan`: Scan multiple pairs for current regimes
- `list_supported_events`: List all supported events and pairs