import os
import json
from pathlib import Path

# Load environment variables
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8127502962:AAHP9nfYJNyoQplbAuNcRsbQNSDKBrsQ5j8")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-1002457519323")

# Default settings
DEFAULT_CHECK_INTERVAL = 10  # Default 10 minutes
VOLUME_DATA_PATH = "./data/volume_data.json"
STORED_CONFIG_PATH = "/data/config.json"

# Default thresholds
THRESHOLDS = {
    "min_market_cap": 100000,  # Minimum market cap in USD
    "min_volume": 10000,       # Minimum 24h volume in USD
    "min_price_change": 1.0,   # Minimum % price change
    "min_liquidity": 10000,    # Minimum liquidity in USD
    "min_buy_sell_ratio": 0.5, # Minimum buy/sell ratio
    "min_rugcheck_score": 70   # Minimum RugCheck safety score
}

# Load initial bot status
BOT_ENABLED = True  # Default to enabled

# Create data directory if it doesn't exist
def ensure_data_dir():
    data_dir = Path("/data")
    if not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

# Try to load configuration from file if it exists
def load_config():
    config_path = Path(STORED_CONFIG_PATH)
    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
                print(f"Loaded config from file: {config}")
                return config
        except Exception as e:
            print(f"Error loading config: {e}")
    return None

# Save configuration to file
def save_config(config):
    ensure_data_dir()
    config_path = Path(STORED_CONFIG_PATH)
    try:
        with open(config_path, "w") as f:
            json.dump(config, f)
            print(f"Saved config to file: {config}")
            return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False

# Load bot status from file
def load_bot_status():
    config = load_config()
    if config and "enabled" in config:
        status = config.get("enabled", BOT_ENABLED)
        print(f"Loaded bot status from file: {config}")
        return status
    return BOT_ENABLED

# Save bot status to file
def save_bot_status(enabled):
    config = load_config() or {}
    config["enabled"] = enabled
    return save_config(config)

# Load check interval from file
def load_check_interval():
    config = load_config()
    if config and "check_interval" in config:
        interval = config.get("check_interval", DEFAULT_CHECK_INTERVAL)
        return interval
    return DEFAULT_CHECK_INTERVAL

# Save check interval to file
def save_check_interval(interval):
    config = load_config() or {}
    config["check_interval"] = interval
    return save_config(config)

# Load thresholds from file or use defaults
def load_thresholds():
    config = load_config()
    if config and "thresholds" in config:
        return config.get("thresholds", THRESHOLDS)
    return THRESHOLDS

# Save thresholds to file
def save_thresholds(thresholds):
    config = load_config() or {}
    config["thresholds"] = thresholds
    return save_config(config)

# Update loaded values from file if available
BOT_ENABLED = load_bot_status()
CHECK_INTERVAL_MINUTES = load_check_interval()
THRESHOLDS = load_thresholds() 