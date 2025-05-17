# Solana Token Tracking Bot (George Bot)

A monitoring and alerting system for Solana tokens that automatically detects promising tokens and sends alerts via Telegram.

## Features

- **Token Discovery**: Monitors new Solana tokens using DexScreener API
- **Filtering System**: Filters tokens based on market cap, volume, price action, and more
- **Safety Checking**: Verifies tokens using RugCheck API to avoid scams
- **Telegram Alerts**: Sends formatted alerts to a Telegram chat
- **Web Dashboard**: ASP.NET Core dashboard for configuration and monitoring
- **API Control**: FastAPI endpoints to control the bot programmatically
- **Resilient Design**: Fault-tolerant architecture that continues working even when external APIs fail
- **Diagnostics**: Tools to test API connections and receive notifications when services recover

## Recent Improvements

- **Enhanced API Integration Resilience**: The system now gracefully handles API failures and rate limits
- **Adaptive Rate Limiting**: Automatically adjusts request rates to prevent hitting API limits
- **Advanced Heuristic Analysis**: Performs basic safety assessment when verification APIs are unavailable
- **Better Caching**: Extended caching system reduces API calls and improves performance
- **Integration Testing**: New endpoint (/test-api-integrations) to check system health and diagnose issues
- **Smart Token Filtering**: Improved token verification process that works even with partial API success

## Project Structure

- **/bot**: Python backend for token tracking and alerting
  - API integrations (DexScreener, Solana RPC, RugCheck)
  - Telegram bot integration
  - Filter logic
  - FastAPI control endpoints
- **/webapp**: ASP.NET Core web dashboard
- **/ml_model**: (Planned) Machine learning components for token analysis

## Setup Instructions

### Prerequisites
- Python 3.8+
- .NET 6.0+ (for web dashboard)
- Docker & Docker Compose (for containerized deployment)
- Telegram Bot Token
- RugCheck API Key (optional)
- Solana RPC URL (optional for better performance)

### Environment Setup

1. Create a `.env` file in the `/bot` directory with the following:

```
# Telegram Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# API Configuration
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
SOLANA_RPC_KEY=your_rpc_key_if_available
RUGCHECK_API_URL=https://api.rugcheck.xyz/v1
RUGCHECK_API_KEY=your_rugcheck_api_key
DEXSCREENER_API_URL=https://api.dexscreener.com/latest/dex

# Bot Configuration
BOT_ENABLED=true
CHECK_INTERVAL_MINUTES=10

# Default Thresholds
MIN_MARKET_CAP=500000
MIN_VOLUME=300000
MIN_PRICE_CHANGE=20
MIN_LIQUIDITY=100000
MIN_BUY_SELL_RATIO=2.0
MIN_RUGCHECK_SCORE=80
```

2. Install Python dependencies:

```bash
cd bot
pip install -r requirements.txt
```

3. Install .NET dependencies (for webapp):

```bash
cd webapp
dotnet restore
```

## Running with Docker

The recommended way to run the system is using Docker Compose:

```bash
docker-compose up -d
```

This will start both the bot and webapp containers with proper networking.

## Running Manually

### Start the Python Bot

```bash
cd bot
python bot.py
```

### Start the API Server

```bash
cd bot
python api.py
```

### Start the Web Dashboard

```bash
cd webapp
dotnet run
```

## API Endpoints

### Bot Control
- `GET /status` - Get bot status
- `POST /toggle` - Enable or disable the bot
- `GET /thresholds` - Get current filter thresholds
- `POST /thresholds` - Update filter thresholds
- `POST /check-now` - Trigger an immediate token check
- `GET /tokens` - Get list of processed tokens

### Token Verification
- `GET /verify-token/{token_address}` - Verify a specific token
- `POST /verify-and-alert/{token_address}` - Verify and send an alert for a token

### System Administration
- `GET /health` - Health check endpoint
- `GET /test-api-integrations` - Test all API integrations and report status
- `POST /send-thresholds-telegram` - Send current thresholds to Telegram

## Handling API Failures

The system employs several strategies to handle external API failures:

1. **Multiple Endpoint Attempts**: Each API integration tries multiple endpoints/domains
2. **Fallback Logic**: If verification APIs fail, the system uses built-in heuristics
3. **Success Rate Calculation**: Tokens are processed as long as a majority of APIs succeed
4. **Notification System**: The system can notify when APIs recover

## Testing

Individual API components can be tested using the test scripts:

```bash
cd bot
python test_dexscreener.py
python test_solana.py
python test_rugcheck.py
python test_telegram.py
```

## License

MIT

## Author

User: diogocheng 
