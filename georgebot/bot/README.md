# Solana Token Bot

A Python bot that tracks Solana tokens using the DexScreener API and sends trading signals via Telegram.

## Features

- **Real-time Token Data**: Fetches Solana token data from DexScreener API
- **Configurable Filters**: Filter tokens based on market cap, volume, price change, liquidity, and buy/sell ratio
- **Telegram Alerts**: Automatically sends alerts for tokens that match criteria
- **REST API**: Control the bot via a REST API to integrate with the web dashboard
- **Alert History**: Keeps track of sent alerts for reference
- **Flexible Configuration**: Update thresholds and bot settings on the fly
- **Resilient API Integration**: Gracefully handles API failures and rate limits
- **Safety Verification**: Validates tokens using Solana RPC and RugCheck APIs
- **Heuristic Analysis**: Performs basic safety checks when verification APIs fail

## API Integrations

- **DexScreener**: For token discovery and market metrics
- **Solana RPC**: To validate tokens and fetch contract information
- **RugCheck**: For safety scoring and scam detection
- **Telegram**: For sending alerts and notifications

## Installation

1. Create a Python virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file with the following content:
   ```
   # Telegram Bot Configuration
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   TELEGRAM_CHAT_ID=your_chat_id

   # API Configuration
   DEXSCREENER_API_URL=https://api.dexscreener.com/latest/dex
   SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
   SOLANA_RPC_KEY=your_rpc_key_if_available
   RUGCHECK_API_URL=https://api.rugcheck.xyz/v1
   RUGCHECK_API_KEY=your_rugcheck_api_key

   # Bot Configuration
   BOT_ENABLED=true
   CHECK_INTERVAL_MINUTES=10

   # Filter Thresholds (defaults, can be changed via API)
   MIN_MARKET_CAP=500000
   MIN_VOLUME=300000
   MIN_PRICE_CHANGE=20
   MIN_LIQUIDITY=100000
   MIN_BUY_SELL_RATIO=2.0
   MIN_RUGCHECK_SCORE=80
   ```

## Usage

### Running the Bot

To start the bot directly:

```bash
python bot.py
```

### Running the API Server

To start the API server (recommended when using with the web dashboard):

```bash
python api.py
```

The API will be available at http://localhost:8000/

## API Endpoints

### Bot Control
- `GET /status` - Get current bot status
- `POST /toggle` - Enable/disable the bot
- `GET /thresholds` - Get current threshold values
- `POST /thresholds` - Update threshold values
- `GET /alerts` - Get recent alert history
- `POST /check-now` - Trigger an immediate token check
- `POST /check-interval/{minutes}` - Update check interval

### Token Verification
- `GET /verify-token/{token_address}` - Verify a specific token
- `POST /verify-and-alert/{token_address}` - Verify and send an alert for a token

### System Administration
- `GET /health` - Health check endpoint
- `GET /test-api-integrations` - Test all API integrations and report status
- `POST /send-thresholds-telegram` - Send current thresholds to Telegram

## Resilient Design

The bot uses several strategies to ensure continued operation even when external APIs fail:

1. **Multiple Endpoint Attempts**: Each API integration tries multiple endpoints/domains
2. **Adaptive Rate Limiting**: Automatically adjusts request rates to avoid hitting rate limits
3. **Extensive Caching**: Caches API responses to reduce calls and improve performance
4. **Fallback Logic**: Uses built-in heuristics when verification APIs fail
5. **Success Rate Calculation**: Processes tokens as long as a majority of APIs succeed

## Project Structure

- `bot.py` - Main bot logic and scheduler
- `dexscreener.py` - DexScreener API integration for token discovery
- `rugcheck.py` - RugCheck API integration for safety verification
- `solana_verify.py` - Solana RPC integration for token validation
- `telegram_alert.py` - Telegram messaging service
- `config.py` - Configuration and settings loader
- `api.py` - REST API for bot control
- `.env` - Environment variables (not in repository)

## Integrating with the Web Dashboard

The bot exposes a REST API that integrates with the ASP.NET Core web dashboard. The dashboard communicates with this API to control the bot and display its status.

## Docker Support

The bot can be run in a Docker container using the provided Dockerfile:

```bash
docker build -t solana-token-bot .
docker run -p 8000:8000 --env-file .env solana-token-bot
```

Or use Docker Compose to run both the bot and webapp:

```bash
docker-compose up -d
```

## License

MIT 