# EventVol Intelligence MCP Server

A Model Context Protocol (MCP) server that provides statistical analysis of FX volatility around macro economic events. This server helps traders and analysts understand expected price movements and volatility patterns during major economic announcements.

## Features

- **Event Volatility Analysis**: Analyze expected price deviations for FX pairs during macro events (NFP, CPI, FOMC, etc.)
- **Probability Calculations**: Calculate breakout and fakeout probabilities based on historical data
- **Volatility Regimes**: Determine current volatility regimes for different currency pairs
- **Multi-Pair Support**: Support for multiple FX pairs including EURUSD, GBPUSD, USDJPY, USDCAD, and more
- **Real-time Data**: Uses Twelve Data API for current market data
- **HTTP/SSE Transport**: FastAPI-based server with Server-Sent Events for real-time communication

## Supported Events

| Event | Description | Typical Time (UTC) | Primary Pairs |
|-------|-------------|-------------------|---------------|
| NFP | US Non-Farm Payrolls | 13:30 (1st Friday) | EURUSD, GBPUSD, USDJPY, USDCAD |
| CPI | US Consumer Price Index | 13:30 | EURUSD, GBPUSD, USDJPY |
| FOMC | Federal Open Market Committee | 19:00 | EURUSD, GBPUSD, USDJPY, XAUUSD |
| ECB | European Central Bank | 13:45 | EURUSD, EURGBP, EURJPY |
| BOE | Bank of England | 12:00 | GBPUSD, EURGBP, GBPJPY |
| PPI | US Producer Price Index | 13:30 | EURUSD, USDJPY |
| RETAIL_SALES | US Retail Sales | 13:30 | EURUSD, GBPUSD |

## HTTP/SSE Transport & Deployment

This server uses a FastAPI + Server-Sent Events transport and can be deployed to Railway, Render, Fly.io, Heroku, or any Python host.

### Available Endpoints

- `GET /` → Tool metadata JSON (name, tools, pricing)
- `GET /health` → Health check (`{"status": "ok"}`)
- `GET /sse` → Opens SSE stream for MCP communication
- `POST /messages` → Accepts MCP JSON-RPC messages

### Environment Variables

```bash
TWELVE_DATA_API_KEY=your_key_here
PORT=8000  # Optional, defaults to 8000
```

### Deployment Files

- `Procfile`: `web: python server.py`
- `runtime.txt`: `python-3.11.9` (for Heroku deployment)

## Installation & Setup

### Prerequisites

- Python 3.11.9 or later
- Twelve Data API key ([Get one here](https://twelvedata.com/))

### Local Development

1. **Clone the repository** (if applicable) and navigate to the project directory

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**:
   Create a `.env` file in the root directory:
   ```
   TWELVE_DATA_API_KEY=your_actual_api_key_here
   ```

4. **Run the server locally**:
   ```bash
   python server.py
   ```

5. **Verify the server is running**:
   - Health check: `http://localhost:8000/health`
   - Tool metadata: `http://localhost:8000/`

## Usage

### MCP Client Integration

Once integrated with an MCP client (like Claude Desktop), you can ask questions such as:

- "What is the expected volatility for GBPUSD during NFP?"
- "Scan volatility regimes for EURUSD, GBPUSD, USDJPY on CPI"
- "What events are supported and their timings?"
- "Analyze breakout probability for USDJPY during FOMC"

### API Usage Examples

#### Get Event Volatility Projection
```json
{
  "method": "tools/call",
  "params": {
    "name": "event_volatility_projection",
    "arguments": {
      "pair": "EURUSD",
      "event": "NFP",
      "lookback_events": 24
    }
  }
}
```

#### Scan Multiple Pairs for Volatility Regimes
```json
{
  "method": "tools/call",
  "params": {
    "name": "volatility_regime_scan",
    "arguments": {
      "pairs": ["EURUSD", "GBPUSD", "USDJPY"],
      "event": "CPI"
    }
  }
}
```

#### List Supported Events
```json
{
  "method": "tools/call",
  "params": {
    "name": "list_supported_events",
    "arguments": {}
  }
}
```

## Tools

### `event_volatility_projection`
**Purpose**: Get detailed volatility projection for a specific FX pair and macro event.

**Parameters**:
- `pair` (string): FX pair (e.g., EURUSD, USDJPY, GBPUSD)
- `event` (string): Macro event (NFP, CPI, FOMC, ECB, BOE, PPI, RETAIL_SALES)
- `lookback_events` (integer, optional): Number of past events to analyze (default: 24, max: 48)

**Returns**: Expected deviation, breakout probability, volatility regime, and confidence metrics.

### `volatility_regime_scan`
**Purpose**: Scan volatility regimes for multiple FX pairs for a given event.

**Parameters**:
- `pairs` (array): List of FX pairs to scan
- `event` (string): Macro event to analyze

**Returns**: Volatility regime analysis for each pair including median deviation and confidence scores.

### `list_supported_events`
**Purpose**: List all supported macro events and their primary FX pairs.

**Parameters**: None

**Returns**: Array of events with UTC timing and associated currency pairs.

## Development

### Running Tests

```bash
python test_local.py
```

### Code Structure

- `server.py`: Main FastAPI server with MCP integration
- `test_local.py`: Local testing utilities
- `requirements.txt`: Python dependencies
- `runtime.txt`: Python version specification
- `Procfile`: Deployment configuration

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This tool provides statistical analysis based on historical data and should not be considered as financial advice. Always perform your own due diligence and risk assessment before making trading decisions.
