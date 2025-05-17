import os
from dotenv import load_dotenv
import json
from pathlib import Path

# Load environment variables from .env file
load_dotenv()

# Telegram Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# API URLs
DEXSCREENER_API_URL = os.getenv("DEXSCREENER_API_URL", "https://api.dexscreener.com/latest/dex")

# Solana RPC API
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
SOLANA_RPC_KEY = os.getenv("SOLANA_RPC_KEY", "")

# RugCheck API
RUGCHECK_API_URL = os.getenv("RUGCHECK_API_URL", "https://api.rugcheck.xyz/v1")
RUGCHECK_API_KEY = os.getenv("RUGCHECK_API_KEY", "")

# Config files
CONFIG_DIR = Path("/app/data")
CONFIG_DIR.mkdir(exist_ok=True)  # Ensure the directory exists
FILTER_CONFIG_FILE = CONFIG_DIR / "filter_config.json"
STATUS_CONFIG_FILE = CONFIG_DIR / "bot_status.json"

# Function to load bot status from the config file
def load_bot_status():
    if STATUS_CONFIG_FILE.exists():
        try:
            with open(STATUS_CONFIG_FILE, "r") as f:
                status_data = json.load(f)
                print(f"Loaded bot status from file: {status_data}")
                return status_data.get("enabled", False)  # Default to False if not found
        except Exception as e:
            print(f"Error loading bot status file: {e}")
    return os.getenv("BOT_ENABLED", "false").lower() == "true"  # Default to false if no file exists

# Function to save bot status to the config file
def save_bot_status(enabled):
    try:
        status_data = {"enabled": enabled}
        print(f"Saving bot status to {STATUS_CONFIG_FILE}")
        
        # Check if directory exists and is writable
        if not CONFIG_DIR.exists():
            print(f"Creating directory {CONFIG_DIR}")
            CONFIG_DIR.mkdir(exist_ok=True)
            
        print(f"Directory exists: {CONFIG_DIR.exists()}, is writable: {os.access(CONFIG_DIR, os.W_OK)}")
        
        with open(STATUS_CONFIG_FILE, "w") as f:
            json.dump(status_data, f, indent=4)
        print(f"Successfully saved bot status: {enabled}")
        return True
    except Exception as e:
        print(f"Error saving bot status file: {e}")
        import traceback
        print(traceback.format_exc())
        return False

# Bot Configuration
BOT_ENABLED = load_bot_status()
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "10"))

# Default Filter Thresholds
DEFAULT_THRESHOLDS = {
    "min_market_cap": float(os.getenv("MIN_MARKET_CAP", "500000")),
    "min_volume": float(os.getenv("MIN_VOLUME", "300000")),
    "min_price_change": float(os.getenv("MIN_PRICE_CHANGE", "20")),
    "min_liquidity": float(os.getenv("MIN_LIQUIDITY", "100000")),
    "min_buy_sell_ratio": float(os.getenv("MIN_BUY_SELL_RATIO", "2.0")),
    "min_rugcheck_score": float(os.getenv("MIN_RUGCHECK_SCORE", "80"))
}

# Function to load thresholds from the config file
def load_thresholds():
    if FILTER_CONFIG_FILE.exists():
        try:
            with open(FILTER_CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config file: {e}")
    return DEFAULT_THRESHOLDS

# Function to save thresholds to the config file
def save_thresholds(thresholds):
    try:
        with open(FILTER_CONFIG_FILE, "w") as f:
            json.dump(thresholds, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving config file: {e}")
        return False

# Global thresholds (will be used by the bot)
THRESHOLDS = load_thresholds()
