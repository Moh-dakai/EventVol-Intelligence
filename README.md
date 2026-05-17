# EventVol Intelligence {Event-Adjusted FX Volatility Projection Engine}
_A Model Context Protocol (MCP) server that analyzes FX market volatility around macro-economic events. Provides expected pip deviation, breakout probability, fakeout scores, and volatility regime classification leveraging historical price patterns and economic calendar data._

<p align="center">
  
[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-1.0+-orange.svg)](https://modelcontextprotocol.io/)
[![Marketplace](https://img.shields.io/badge/Marketplace-CTX%20Protocol-blue.svg)](https://www.ctxprotocol.com/)

</p>
<
##  Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Reference](#api-reference)
- [Project Structure](#project-structure)
- [Data Flow](#data-flow)
- [Testing](#testing)
- [Contributing](#contributing)
- [License](#license)

##  Overview

EventVol Intelligence is an MCP server that analyzes historical forex price behavior during macro-economic events (NFP, CPI, FOMC, ECB, BOE, PPI, Retail Sales) to project expected volatility and trading patterns. It combines:

- **Economic calendar integration** with precise historical event dates
- **1-hour candle analysis** covering 200+ days of historical data via Twelve Data API
- **Statistical pattern matching** to identify similar historical conditions
- **Volatility metrics** including expected deviation, breakout probability, and fakeout scores
- **Regime classification** (Compressed/Normal/Expansionary) based on recent market activity
- **Confidence scoring** weighted by sample size and variance consistency

The server exposes three MCP tools that accept FX pairs and event types, returning comprehensive statistical analysis including pip ranges, probability metrics, and session bias information to inform trading decisions.

##  Key Features

###  Event-Driven Analysis
- **Historical Event Matching**: Links economic events to precise historical release times via Finnhub calendar or hardcoded event dates
- **Multi-Event Support**: NFP, CPI, FOMC, ECB, BOE, PPI, Retail Sales
- **Pattern Recognition**: Finds all matching events in historical candle data and analyzes price action around each release
- **Session Classification**: Identifies which trading session the event occurs in (Asia/London/NY)

###  Volatility Metrics
- **Expected Deviation**: Median pip range during first 2 hours after event (immediate reaction)
- **Extended Range**: 4-hour post-event pip movement for full reaction analysis
- **Breakout Probability**: Percentage of events that resulted in directional continuation
- **Fakeout Likelihood**: Probability of mean reversion or failed breakouts
- **Confidence Score**: Statistical confidence based on sample size and variance

###  Regime Classification
- **Compressed**: Recent average volatility <75% of historical mean (potential breakout setup)
- **Normal**: Recent activity within 75-130% of historical mean
- **Expansionary**: Recent volatility >130% of historical mean

###  Developer-Friendly
- **MCP Protocol**: Standards-compliant MCP server using SSE transport
- **HTTP/REST API**: FastAPI-based server with JSON responses
- **Caching**: Built-in response caching to reduce API calls
- **Error Handling**: Graceful handling of insufficient data and API errors

##  Architecture

EventVol follows a clean event-to-analysis pipeline:

```
┌─────────────────────────────────────────────────────────────────┐
│  External Data Sources                                          │
│  ├── Finnhub Economic Calendar API (Event dates)                │
│  ├── Twelve Data API (1H forex candles)                         │
│  └── Hardcoded Event Dates (Fallback)                           │
└────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  MCP Server (server.py)                                         │
│  ├── SSE Transport for MCP Protocol                             │
│  ├── Tool Definition Layer                                      │
│  └── FastAPI HTTP Wrapper                                       │
└────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  EventVolServer Class                                           │
│  ├── fetch_candles() - Retrieves 1H OHLCV data                  │
│  ├── event_volatility_projection() - Main analysis              │
│  ├── volatility_regime_scan() - Multi-pair scan                 │
│  └── list_supported_events() - Event metadata                   │
└────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Analysis Layer                                                 │
│  ├── compute_event_stats() - Range calculations                 │
│  ├── Pattern Matching - Event date alignment to candles         │
│  ├── Probability Calculation - Breakout/fakeout stats           │
│  └── Regime Classification - Volatility regime detection        │
└────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Response Layer                                                 │
│  ├── Statistical metrics (deviation, probability, confidence)   │
│  ├── Regime classification and sample data                      │
│  └── Event dates used and data source attribution               │
└────────────────────────────────────────────────────────────────┘
```

### Core Components

- **MCP Server**: Handles MCP protocol communication and tool exposure
- **Twelve Data Client**: Fetches historical 1-hour candles for analysis
- **Finnhub Calendar Client**: Retrieves real historical event release dates
- **Event Analyzer**: Matches events to candles and computes statistics
- **Regime Classifier**: Categorizes current volatility environment

##  Installation

### Prerequisites

- Python 3.11.9 or higher
- Twelve Data API key ([Get one here](https://twelvedata.com/) - free tier available)
- Finnhub API key (optional, for live event calendar) ([Get one here](https://finnhub.io/))

### Step 1: Clone the Repository

```bash
git clone https://github.com/your-org/EventVol-Intelligence.git
cd EventVol-Intelligence
```

### Step 2: Create Virtual Environment

```bash
# Create virtual environment
python -m venv .venv

# Activate it
source .venv/bin/activate  # Linux/Mac
# OR
.venv\Scripts\activate     # Windows
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Set Environment Variables

Create a `.env` file in the project root:

```bash
TWELVE_DATA_API_KEY=your_api_key_here
FINNHUB_API_KEY=your_finnhub_key_here  # Optional
PORT=8000
```

### Step 5: Verify Installation

```bash
# Test import
python -c "from server import EventVolServer; print('Installation successful')"
```

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Required
TWELVE_DATA_API_KEY=your_api_key_here

# Optional: For live economic calendar integration
FINNHUB_API_KEY=your_finnhub_key_here

# Optional: Server configuration
PORT=8000
LOG_LEVEL=INFO
```

### API Keys

**Twelve Data:**
- Free tier: 800 requests/day
- Used for fetching 1-hour OHLCV candle data
- Sign up at https://twelvedata.com/

**Finnhub (Optional):**
- Free tier available
- Used to fetch real historical event release dates
- Falls back to hardcoded event dates if unavailable
- Sign up at https://finnhub.io/

### Data Caching

The server includes response caching to reduce API calls:
- **Candle Cache TTL**: 300 seconds
- **Event Date Cache TTL**: 3600 seconds
- Automatic cache invalidation based on time-to-live

## Usage

### MCP Server (Production)

Run the MCP server with SSE transport:

```bash
python server.py
```

The server runs on `http://localhost:8000` by default.

### Integration with Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "eventvol": {
      "command": "python",
      "args": ["server.py"],
      "env": {
        "TWELVE_DATA_API_KEY": "your_api_key_here",
        "FINNHUB_API_KEY": "your_finnhub_key_here"
      }
    }
  }
}
```

### Endpoints

When server is running:

- `GET /` - Server info and available tools
- `GET /health` - Health check
- `GET /sse` - SSE stream for MCP protocol
- `POST /messages` - Accept MCP messages

### Example Usage

Once integrated with an MCP client, you can ask:

```
"What is the expected volatility for EURUSD during NFP?"
"Scan volatility regimes for EURUSD, GBPUSD, USDJPY on CPI"
"What macro events are supported?"
"Analyze breakout probability for USDJPY during FOMC"
```

## API Reference

### Tool 1: `event_volatility_projection`

Analyzes historical volatility pattern for a specific FX pair during a macro event.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pair` | string | Yes | FX pair (e.g., "EURUSD", "GBPUSD", "USDJPY") |
| `event` | string | Yes | Event: NFP, CPI, FOMC, ECB, BOE, PPI, RETAIL_SALES |
| `lookback_events` | integer | No | Number of past events to analyze (default: 24, max: 48) |

#### Response

```json
{
  "pair": "EURUSD",
  "event": "NFP",
  "success": true,
  "dataAvailable": true,
  "sample_size": 24,
  "expected_deviation_pips": 67.3,
  "mean_deviation_pips": 71.2,
  "p75_deviation_pips": 95.4,
  "h4_range_median_pips": 103.5,
  "breakout_probability": 0.58,
  "mean_reversion_probability": 0.42,
  "fakeout_likelihood_score": 0.42,
  "volatility_regime": "Normal",
  "confidence_score": 0.87,
  "session_bias": "NY",
  "event_dates_used": ["2025-05-02", "2025-04-04", "2025-03-07"],
  "low_sample_warning": false,
  "data_source": "Finnhub economic calendar + Twelve Data 1H candles",
  "analysis_timestamp": "2026-05-17T10:30:00Z"
}
```

### Tool 2: `volatility_regime_scan`

Scans multiple FX pairs and returns their volatility regime classification for a given event.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pairs` | array | Yes | List of FX pairs (e.g., ["EURUSD", "GBPUSD", "USDJPY"]) |
| `event` | string | No | Event type (default: "NFP") |
| `lookback_events` | integer | No | Number of past events (default: 24) |

#### Response

```json
{
  "event_context": "NFP",
  "results": [
    {
      "pair": "EURUSD",
      "regime": "Normal",
      "median_dev_pips": 67.3,
      "confidence": 0.87
    },
    {
      "pair": "GBPUSD",
      "regime": "Compressed",
      "median_dev_pips": 52.1,
      "confidence": 0.81
    },
    {
      "pair": "USDJPY",
      "regime": "Expansionary",
      "median_dev_pips": 89.7,
      "confidence": 0.79
    }
  ],
  "timestamp": "2026-05-17T10:30:00Z"
}
```

### Tool 3: `list_supported_events`

Lists all supported macro events and their availability.

#### Parameters

None

#### Response

```json
{
  "supported_events": {
    "NFP": {
      "total_dates_available": 48,
      "earliest": "2022-01-07",
      "latest": "2025-12-05",
      "utc_hour": 13
    },
    "CPI": {
      "total_dates_available": 47,
      "earliest": "2022-01-12",
      "latest": "2025-12-10",
      "utc_hour": 13
    },
    "FOMC": {
      "total_dates_available": 32,
      "earliest": "2022-03-16",
      "latest": "2026-03-18",
      "utc_hour": 19
    },
    "ECB": {
      "total_dates_available": 32,
      "earliest": "2022-02-03",
      "latest": "2025-12-18",
      "utc_hour": 13
    },
    "BOE": {
      "total_dates_available": 32,
      "earliest": "2022-02-03",
      "latest": "2025-12-18",
      "utc_hour": 12
    },
    "PPI": {
      "total_dates_available": 44,
      "earliest": "2022-01-13",
      "latest": "2025-12-11",
      "utc_hour": 13
    },
    "RETAIL_SALES": {
      "total_dates_available": 44,
      "earliest": "2022-01-14",
      "latest": "2025-12-16",
      "utc_hour": 13
    }
  }
}
```

### Response Metrics Explained

| Metric | Description |
|--------|-------------|
| `expected_deviation_pips` | Median pip range in first 2 hours after event |
| `p75_deviation_pips` | 75th percentile pip range (worst case typical) |
| `h4_range_median_pips` | Median pip range over 4 hours post-event |
| `breakout_probability` | % of events resulting in directional continuation |
| `mean_reversion_probability` | % of events resulting in pullback/fakeout |
| `fakeout_likelihood_score` | Probability of trend reversal |
| `volatility_regime` | Compressed/Normal/Expansionary classification |
| `confidence_score` | 0-1 reliability score based on sample size and variance |

##  Project Structure

```
EventVol-Intelligence/
├── .env                      # Environment variables (API keys)
├── .gitignore               # Git ignore rules
├── .git/                    # Git repository
├── README.md                # This file
├── requirements.txt         # Python dependencies
├── runtime.txt              # Python version (3.11.9)
├── Procfile                 # Deployment config (web: python server.py)
├── claude_desktop_config.json  # MCP Claude Desktop config
├── server.py                # Main MCP server (EventVolServer class)
├── server_output.log        # Server logs
├── test_local.py            # Local testing utilities
└── tests/                   # Test suite
    ├── test_event_projection_errors.py
    └── test_event_specificity.py
```

### Key Files

- **server.py**: Main MCP server implementation with EventVolServer class and MCP tools
- **requirements.txt**: Dependencies (mcp, httpx, starlette, uvicorn, etc.)
- **test_local.py**: Local testing utilities and mock data
- **tests/**: Comprehensive test suite for analysis and projections

##  Data Flow

```
┌─────────────────┐
│  MCP Client     │
│ (Claude, etc)   │
└────────┬────────┘
         │
    Call Tool
         │
         ▼
┌─────────────────────────────┐
│  SSE Transport Handler      │
│  /sse → MCP messages        │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  Tool Handler               │
│  event_volatility_projection│
│  volatility_regime_scan     │
│  list_supported_events      │
└────────┬────────────────────┘
         │
    ┌────┴──────┐
    │            │
    ▼            ▼
┌──────────┐  ┌──────────────────┐
│ Fetch    │  │ Get Event Dates  │
│ Candles  │  │ (Finnhub/Cache)  │
└────┬─────┘  └────────┬─────────┘
     │                 │
     ▼                 ▼
┌──────────────────────────────┐
│ Twelve Data API              │
│ (1H OHLCV candles)           │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ Event Date Matching          │
│ Find candle index per event  │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ Compute Event Statistics     │
│ • Range calculations         │
│ • Breakout/fakeout analysis  │
│ • Volatility regime class    │
│ • Confidence scoring         │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ Format Response              │
│ • Metrics and confidence     │
│ • Event dates used           │
│ • Data source attribution    │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ Return to MCP Client         │
│ JSON Response                │
└──────────────────────────────┘
```

### Analysis Pipeline

1. **Receive Request**: User specifies pair, event, lookback period
2. **Fetch Event Dates**: Query Finnhub calendar or use hardcoded dates
3. **Fetch Candles**: Retrieve 1-hour OHLCV data for ~200 days
4. **Match Events to Candles**: Find candle index for each event date
5. **Calculate Ranges**: High/low over 2H and 4H windows
6. **Compute Probabilities**: Breakout vs mean reversion frequency
7. **Classify Regime**: Compare recent volatility to historical mean
8. **Score Confidence**: Weight by sample size and variance consistency
9. **Return Metrics**: All statistics aggregated and formatted

##  Testing

EventVol includes a test suite for validation and development:

### Running Tests

```bash
# Run all tests
python -m pytest tests/

# Run specific test file
python -m pytest tests/test_event_projection_errors.py
python -m pytest tests/test_event_specificity.py

# Run with verbose output
python -m pytest tests/ -v

# Run local test script
python test_local.py
```

### Test Files

- **test_event_projection_errors.py**: Tests error handling and edge cases
- **test_event_specificity.py**: Tests accuracy of event date matching and volatility calculations

### Test Coverage

Tests validate:
- Event date matching accuracy
- Volatility projection calculations
- Probability metrics computation
- Regime classification logic
- Error handling for API failures
- Insufficient data scenarios

### Running the Server Locally

```bash
# Start development server
python server.py

# Check health
curl http://localhost:8000/health

# View server info
curl http://localhost:8000/

# Send test MCP message (via SSE stream)
# Use MCP-compatible client like Claude Desktop
```

### Development Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Set up development environment (see Installation)
4. Make your changes to server.py or tests
5. Run tests: `python -m pytest tests/`
6. Commit changes: `git commit -am 'Add your feature'`
7. Push to branch: `git push origin feature/your-feature`
8. Create Pull Request

### Code Standards

- Follow PEP 8 style guidelines
- Add type hints for function parameters and return values
- Write comprehensive docstrings
- Add unit tests for new functionality
- Update README.md if adding new features
##  License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

##  Disclaimer

This tool provides statistical analysis based on historical price patterns during economic events and should not be considered as financial advice. Always perform your own due diligence and risk assessment before making trading decisions. Past event volatility is not indicative of future results.

##  Support

- **Issues**: [GitHub Issues](https://github.com/your-username/EventVol-Intelligence/issues)
- **Documentation**: Review this README and test files for examples
- **Contributing**: See Development section above for contribution guidelines
