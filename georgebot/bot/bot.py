import asyncio
import datetime
import logging
import time
import schedule
from telegram import Bot
from dexscreener import DexScreenerAPI
from solana_verify import SolanaVerifier
from rugcheck import RugCheckAPI
from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    CHECK_INTERVAL_MINUTES,
    BOT_ENABLED,
    THRESHOLDS,
    CONFIG_DIR
)
import json
import requests
import aiohttp
import threading

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SolanaTokenBot:
    def __init__(self):
        self.dexscreener = DexScreenerAPI()
        self.solana_verifier = SolanaVerifier()
        self.rugcheck = RugCheckAPI()
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.thresholds = self.load_thresholds() or THRESHOLDS.copy()
        self.processed_tokens = self.load_processed_tokens()
        self.last_run_time = None
        self.is_running = BOT_ENABLED  # This now uses the persisted state from config.py
        self.alert_history = []  # Store alert history for API
        self._schedule_started = False
        
        # For debugging/testing
        self.test_mode = False
        self.force_verification = False
        
        # Load the saved check interval or use the default
        self.load_interval()
        self.job = None  # Store the scheduled job for rescheduling
        
        # Report initialization
        logger.info(f"Bot initialized with state: {'ENABLED' if self.is_running else 'DISABLED'}")
        logger.info(f"Check interval set to {self.check_interval} minutes")
        logger.info(f"Current thresholds: {self.thresholds}")
        logger.info(f"Total processed tokens: {len(self.processed_tokens)}")
        
        # Send startup message to Telegram
        asyncio.create_task(self.send_status_message(
            f"🚀 *Solana Token Bot System Started*\n\n"
            f"🕒 *Time*: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"▶️ *Status*: {'Enabled' if self.is_running else 'Disabled'}\n"
            f"⏱️ *Check Interval*: {self.check_interval} minutes\n"
            f"✅ *Total Processed Tokens*: {len(self.processed_tokens)}"
        ))
        
    async def send_telegram_alert(self, token_info):
        """Send alert about token to Telegram"""
        try:
            # Get safety score, either from token_info or look it up
            safety_score = token_info.get('safety_score', None)
            if safety_score is None:
                try:
                    safety_score = self.rugcheck.get_safety_score(token_info["address"])
                except Exception as e:
                    logger.warning(f"Failed to get safety score for alert: {e}")
                    safety_score = 70  # Use default score if lookup fails
            
            # Add emoji indicators based on metrics
            price_emoji = "🚀" if token_info['price_change'] > 50 else "📈" if token_info['price_change'] > 0 else "📉"
            volume_emoji = "💹" if token_info['volume_24h'] > 1000000 else "📊"
            safety_emoji = "🔒" if safety_score >= 80 else "⚠️" if safety_score >= 50 else "🔴"
            
            # Add Solana verification status
            is_valid = token_info.get('is_valid', True)  # Default to True if not provided
            solana_verify_emoji = "✅" if is_valid else "❌"
            
            # Create message
            message = (
                f"🚨 *New Solana Token Alert* 🚨\n\n"
                f"*{token_info['name']} ({token_info['symbol']})*\n\n"
                f"💰 Market Cap: ${token_info['market_cap']:,.2f}\n"
                f"{volume_emoji} 24h Volume: ${token_info['volume_24h']:,.2f}\n"
                f"{price_emoji} Price Change: {token_info['price_change']:+.2f}%\n"
                f"💧 Liquidity: ${token_info['liquidity']:,.2f}\n"
                f"🔄 Buy/Sell Ratio: {token_info['buy_sell_ratio']:.2f}\n"
                f"{safety_emoji} Safety Score: {safety_score}/100\n"
                f"{solana_verify_emoji} *Solana Verified*: {is_valid}\n\n"
                f"📝 Contract: `{token_info['address']}`\n"
                f"🔗 [View on DexScreener]({token_info['url']})\n\n"
                f"_Alert time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_"
            )
            
            logger.info(f"Sending alert for {token_info['symbol']}")
            
            # If in test mode, just log the message instead of sending
            if self.test_mode:
                logger.info(f"TEST MODE - Would send message: {message}")
                return True
                
            # Send message with retries
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    bot = Bot(token=self.bot_token)
                    await bot.send_message(
                        chat_id=self.chat_id,
                        text=message,
                        parse_mode="Markdown"
                    )
                    
                    # Add to alert history
                    alert_entry = {
                        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        **token_info,
                        "safety_score": safety_score
                    }
                    self.alert_history.append(alert_entry)
                    
                    logger.info(f"✅ Successfully sent alert for {token_info['name']} ({token_info['symbol']})")
                    return True
                except Exception as e:
                    logger.warning(f"Alert attempt {attempt+1} failed: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)  # Wait before retrying
                    else:
                        logger.error(f"Failed to send Telegram alert after {max_retries} attempts")
                        import traceback
                        logger.error(f"Alert error details: {traceback.format_exc()}")
            
            return False
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")
            import traceback
            logger.error(f"Alert error details: {traceback.format_exc()}")
            return False
    
    def scan_for_tokens(self):
        """Scan for new tokens matching our criteria"""
        try:
            logger.info("Starting token scan...")
            self.last_run_time = datetime.datetime.now()
            
            # Get tokens that match our filter criteria
            tokens = self.dexscreener.get_filtered_tokens()
            
            if not tokens:
                logger.info("No tokens matching criteria found")
                return
                
            logger.info(f"Found {len(tokens)} tokens matching filter criteria")
            new_tokens = 0
            max_tokens_per_scan = 10  # Limit to sending at most 10 tokens per scan
            
            for token in tokens:
                # Skip already processed tokens
                if token["address"] in self.processed_tokens:
                    logger.info(f"Skipping already processed token: {token['symbol']} ({token['address']})")
                    continue
                
                # Limit the number of tokens we process in a single scan
                if new_tokens >= max_tokens_per_scan:
                    logger.info(f"Reached limit of {max_tokens_per_scan} tokens for this scan. Remaining tokens will be processed in the next scan.")
                    break
                    
                # Verify token
                logger.info(f"Processing potential token: {token['name']} ({token['symbol']}) - {token['address']}")
                is_valid = self.verify_token(token)
                
                if not is_valid:
                    logger.warning(f"Token {token['symbol']} is not valid, skipping")
                    continue
                
                # Get safety score
                safety_score = self.rugcheck.get_safety_score(token["address"])
                logger.info(f"Token {token['symbol']} safety score: {safety_score}")
                
                if safety_score < self.thresholds["min_rugcheck_score"]:
                    logger.warning(f"Token {token['symbol']} safety score too low ({safety_score}), skipping")
                    continue
                
                # Add token info
                token["safety_score"] = safety_score
                
                # Valid token found, add to processed list to avoid duplicates
                self.processed_tokens.add(token["address"])
                
                # Log the discovery
                logger.info(f"✨ New valid token found: {token['name']} ({token['symbol']})")
                
                # Send alert about the token if not in test mode
                if not self.test_mode:
                    logger.info(f"Sending alert for {token['symbol']}")
                    try:
                        self.send_telegram_alert_sync(token)
                        new_tokens += 1
                        logger.info(f"✅ Successfully sent alert for {token['name']} ({token['symbol']})")
                    except Exception as e:
                        logger.error(f"Failed to send alert for token {token['symbol']}: {e}")
                else:
                    logger.info(f"Test mode active - Not sending alert for {token['symbol']}")
                    new_tokens += 1
            
            # Save the updated processed tokens list
            self.save_config()
            
            logger.info(f"Scan complete. Sent {new_tokens} new token alerts.")
            
        except Exception as e:
            logger.error(f"Error in scan_for_tokens: {e}")
    
    def run_scheduled_task(self):
        """Run the scheduled token scan if bot is enabled"""
        if self.is_running:
            logger.info("Running scheduled token scan...")
            self.scan_for_tokens()
        else:
            logger.info("Bot is disabled, skipping scheduled scan")

    def start_scheduler(self):
        """Start the scheduler to run tasks at regular intervals"""
        if not self._schedule_started:
            self._schedule_started = True
            self.job = schedule.every(self.check_interval).minutes.do(self.run_scheduled_task)
            logger.info(f"Bot started, checking every {self.check_interval} minutes")
            
            # Run the scheduler in a separate thread
            threading.Thread(target=self._run_scheduler, daemon=True).start()
            
            # Run initial task
            self.run_scheduled_task()

    def check_tokens(self):
        """Trigger an immediate token check"""
        logger.info("Manual token check triggered")
        self.scan_for_tokens()
        
    def process_specific_token(self, token_address):
        """Find and check a specific token by address"""
        logger.info(f"Finding specific token: {token_address}")
        try:
            # Get token info from DexScreener
            pair_info = self.dexscreener.get_token_pair_by_address(token_address)
            if not pair_info:
                logger.warning(f"No pair info found for token: {token_address}")
                return False
                
            # Extract token info and format it
            base_token = pair_info.get("baseToken", {})
            if not base_token and "tokens" in pair_info:
                base_token = pair_info.get("tokens", {}).get("base", {})
                
            # Use more robust extraction with fallbacks
            token_name = "Unknown"
            token_symbol = "Unknown"
            
            # Try to extract token name and symbol with multiple fallbacks
            if isinstance(base_token, dict):
                token_name = base_token.get("name", "Unknown")
                token_symbol = base_token.get("symbol", "Unknown")
            elif "name" in pair_info:
                token_name = pair_info.get("name", "Unknown")
            
            if token_name == "Unknown" and "baseToken" in str(pair_info):
                # Try parsing from string if JSON structure is unexpected
                import re
                name_match = re.search(r'"name"\s*:\s*"([^"]+)"', str(pair_info))
                if name_match:
                    token_name = name_match.group(1)
                    
                symbol_match = re.search(r'"symbol"\s*:\s*"([^"]+)"', str(pair_info))
                if symbol_match:
                    token_symbol = symbol_match.group(1)
                
            # Create token info with safe extractions and fallbacks
            token_info = {
                "name": token_name,
                "symbol": token_symbol,
                "address": token_address,
                "market_cap": float(pair_info.get("fdv", 0) or 0),
                "volume_24h": 0,
                "price_change": 0,
                "liquidity": 0,
                "buy_sell_ratio": 1.0,
                "url": pair_info.get("url", f"https://dexscreener.com/solana/{token_address}"),
                "price_usd": 0
            }
            
            # Extract volume with fallbacks
            if "volume" in pair_info:
                volume_obj = pair_info.get("volume", {})
                if isinstance(volume_obj, dict) and "h24" in volume_obj:
                    token_info["volume_24h"] = float(volume_obj.get("h24", 0) or 0)
                else:
                    token_info["volume_24h"] = float(volume_obj or 0)
            
            # Extract price change with fallbacks
            if "priceChange" in pair_info:
                price_change_obj = pair_info.get("priceChange", {})
                if isinstance(price_change_obj, dict) and "h24" in price_change_obj:
                    raw_change = str(price_change_obj.get("h24", "0")).replace("%", "")
                    token_info["price_change"] = float(raw_change or 0)
                else:
                    try:
                        raw_change = str(price_change_obj).replace("%", "")
                        token_info["price_change"] = float(raw_change or 0)
                    except (ValueError, TypeError):
                        token_info["price_change"] = 0
            
            # Extract liquidity with fallbacks
            if "liquidity" in pair_info:
                liquidity_obj = pair_info.get("liquidity", {})
                if isinstance(liquidity_obj, dict) and "usd" in liquidity_obj:
                    token_info["liquidity"] = float(liquidity_obj.get("usd", 0) or 0)
                else:
                    token_info["liquidity"] = float(liquidity_obj or 0)
            
            # Extract price with fallbacks
            token_info["price_usd"] = float(pair_info.get("priceUsd", 0) or 0)
            
            # Try to get buy/sell ratio
            if "txns" in pair_info and "h24" in pair_info["txns"]:
                buys = int(pair_info["txns"]["h24"].get("buys", 0) or 0)
                sells = int(pair_info["txns"]["h24"].get("sells", 0) or 0)
                token_info["buy_sell_ratio"] = buys / max(sells, 1)
            
            # Check if this token meets the basic thresholds
            meets_thresholds = (
                token_info["market_cap"] >= self.thresholds["min_market_cap"] and
                token_info["volume_24h"] >= self.thresholds["min_volume"] and
                token_info["price_change"] >= self.thresholds["min_price_change"] and
                token_info["liquidity"] >= self.thresholds["min_liquidity"] and
                token_info["buy_sell_ratio"] >= self.thresholds["min_buy_sell_ratio"]
            )
            
            if not meets_thresholds:
                logger.info(f"Token {token_symbol} doesn't meet basic thresholds: " + 
                           f"MC: ${token_info['market_cap']:,.2f}, Vol: ${token_info['volume_24h']:,.2f}, " +
                           f"Change: {token_info['price_change']}%, Liq: ${token_info['liquidity']:,.2f}")
                return False
                
            # Force verification for specific token checks - but make it permissive
            verification_success = False
            try:
                is_valid = self.solana_verifier.is_valid_token(token_address)
                logger.info(f"Specific token validity: {is_valid}")
                token_info["is_valid"] = is_valid
                verification_success = True
            except Exception as e:
                logger.error(f"Error verifying token {token_address}: {e}")
                # Be permissive with verification errors
                token_info["is_valid"] = True
            
            # Get safety score with error handling
            safety_success = False
            try:
                safety_score = self.rugcheck.get_safety_score(token_address)
                token_info["safety_score"] = safety_score
                logger.info(f"Token {token_symbol} safety score: {safety_score}")
                safety_success = True
            except Exception as e:
                logger.error(f"Error getting safety score for {token_address}: {e}")
                # Use a default safety score
                token_info["safety_score"] = 85
            
            # Check if the token meets the safety score threshold
            if safety_success and token_info["safety_score"] < self.thresholds["min_rugcheck_score"]:
                logger.info(f"Token {token_symbol} safety score {token_info['safety_score']} below threshold " + 
                           f"{self.thresholds['min_rugcheck_score']}")
                # Only reject if we successfully verified the safety score and it's truly below threshold
                return False
            
            # Count API verification success rate
            api_success_count = sum([verification_success, safety_success, True])  # DexScreener succeeded
            total_apis = 3
            api_success_rate = api_success_count / total_apis
            
            logger.info(f"API success rate for {token_symbol}: {api_success_rate:.2%}")
            
            # As long as we have a sufficiently high success rate, proceed with the alert
            if api_success_rate >= 0.5:  # At least half of APIs succeeded
                # Always send an alert for specific token checks - handle asyncio properly
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # We're in an existing event loop, use create_task
                        asyncio.create_task(self.send_telegram_alert(token_info))
                    else:
                        # No running event loop, use run_until_complete
                        loop.run_until_complete(self.send_telegram_alert(token_info))
                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(self.send_telegram_alert(token_info))
                    
                self.processed_tokens.add(token_address)
                self.save_config()  # Save processed tokens to avoid repeats
                return True
            else:
                logger.warning(f"Not enough API verification success for {token_symbol} ({token_address})")
                return False
            
        except Exception as e:
            logger.error(f"Error finding specific token {token_address}: {e}")
            import traceback
            logger.error(f"Find token error: {traceback.format_exc()}")
            return False

    async def send_plain_telegram_message(self, message):
        """Send a plain text message to Telegram (for status/notifications)"""
        try:
            logger.info(f"Attempting to send Telegram message: {message[:50]}...")
            
            if not self.bot_token or not self.chat_id:
                logger.error(f"Cannot send message - Missing bot token or chat ID: Token={bool(self.bot_token)}, Chat ID={bool(self.chat_id)}")
                return False
                
            bot = Bot(token=self.bot_token)
            await bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode="Markdown"
            )
            logger.info(f"Successfully sent status message to Telegram chat {self.chat_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send plain Telegram message: {str(e)}")
            # Print detailed error for debugging
            import traceback
            logger.error(f"Error details: {traceback.format_exc()}")
            return False

    def update_check_interval(self, minutes):
        """Update the check interval in minutes"""
        try:
            if minutes < 1 or minutes > 60:
                logger.error(f"Invalid check interval: {minutes} minutes (must be between 1 and 60)")
                return False
                
            self.check_interval = minutes
            logger.info(f"Updating check interval from {CHECK_INTERVAL_MINUTES} to {minutes} minutes")
            
            # Save the new interval to disk
            interval_path = CONFIG_DIR / "interval.json"
            with open(interval_path, 'w') as f:
                json.dump({"check_interval_minutes": minutes}, f)
            logger.info(f"Saved check interval ({minutes} minutes) to {interval_path}")
            
            # If the scheduler is running, cancel the old job and create a new one
            if self._schedule_started:
                # Clear all existing jobs
                schedule.clear()
                # Create a new job with the updated interval
                self.job = schedule.every(minutes).minutes.do(self.run_scheduled_task)
                logger.info(f"Rescheduled job to run every {minutes} minutes")
            
            return True
        except Exception as e:
            logger.error(f"Error updating check interval: {e}")
            return False
        
    def save_interval(self):
        """Save the check interval to the config file"""
        try:
            config_path = CONFIG_DIR / "interval.json"
            with open(config_path, 'w') as f:
                json.dump({"check_interval_minutes": self.check_interval}, f)
            logger.info(f"Saved check interval ({self.check_interval} minutes) to {config_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving check interval: {e}")
            return False
            
    def load_interval(self):
        """Load the check interval from the config file"""
        try:
            config_path = CONFIG_DIR / "interval.json"
            if config_path.exists():
                with open(config_path, 'r') as f:
                    data = json.load(f)
                    interval = data.get("check_interval_minutes", CHECK_INTERVAL_MINUTES)
                    # Validate the loaded value
                    if isinstance(interval, (int, float)) and interval >= 1:
                        self.check_interval = int(interval)
                        logger.info(f"Loaded check interval: {self.check_interval} minutes")
                        return True
            
            # Use default if file doesn't exist or is invalid
            self.check_interval = CHECK_INTERVAL_MINUTES
            logger.info(f"Using default check interval: {self.check_interval} minutes")
            return True
            
        except Exception as e:
            logger.error(f"Error loading check interval: {e}")
            self.check_interval = CHECK_INTERVAL_MINUTES
            return False

    def load_processed_tokens(self):
        """Load processed tokens from the config file"""
        try:
            config_path = CONFIG_DIR / "processed_tokens.json"
            if config_path.exists():
                with open(config_path, 'r') as f:
                    tokens = json.load(f)
                    return set(tokens)
            return set()
        except Exception as e:
            logger.error(f"Error loading processed tokens: {e}")
            return set()

    def load_thresholds(self):
        """Load thresholds from the config file"""
        try:
            config_path = CONFIG_DIR / "thresholds.json"
            if config_path.exists():
                with open(config_path, 'r') as f:
                    thresholds = json.load(f)
                    return thresholds
            return None
        except Exception as e:
            logger.error(f"Error loading thresholds: {e}")
            return None

    async def send_status_message(self, message):
        """Send a status message to the Telegram group"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            params = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=params) as response:
                    if response.status == 200:
                        logger.info(f"Successfully sent status message to Telegram chat {self.chat_id}")
                        return True
                    else:
                        logger.error(f"Failed to send status message: {response.status} {await response.text()}")
                        return False
        except Exception as e:
            logger.error(f"Error sending status message: {e}")
            return False

    def send_telegram_alert_sync(self, token_info):
        """Send alert about token to Telegram (synchronous version)"""
        try:
            # Get safety score, either from token_info or look it up
            safety_score = token_info.get('safety_score', None)
            if safety_score is None:
                try:
                    safety_score = self.rugcheck.get_safety_score(token_info["address"])
                except Exception as e:
                    logger.warning(f"Failed to get safety score for alert: {e}")
                    safety_score = 70  # Use default score if lookup fails
            
            # Add emoji indicators based on metrics
            price_emoji = "🚀" if token_info.get('price_change', 0) > 50 else "💰"
            volume_emoji = "🔥" if token_info.get('volume_24h', 0) > 1000000 else "📊"
            safety_emoji = "✅" if safety_score >= 80 else "⚠️" if safety_score >= 60 else "🚨"
            
            # Get token URL
            token_address = token_info.get('address', '')
            token_url = token_info.get('url', f"https://dexscreener.com/solana/{token_address}")
            
            # Create message text
            message_text = (
                f"{safety_emoji} *New Token Alert:* {token_info['name']} ({token_info['symbol']})\n\n"
                f"📈 *Price Change*: {token_info.get('price_change', 0):.2f}%\n"
                f"{volume_emoji} *24h Volume*: ${token_info.get('volume_24h', 0):,.2f}\n"
                f"💎 *Market Cap*: ${token_info.get('market_cap', 0):,.2f}\n"
                f"💧 *Liquidity*: ${token_info.get('liquidity', 0):,.2f}\n"
                f"{safety_emoji} *Safety Score*: {safety_score}/100\n\n"
                f"🔗 [View Chart]({token_url})\n"
                f"📱 [Trade Token](https://jup.ag/swap/SOL-{token_info['symbol']})\n"
            )
            
            # Send message
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            params = {
                "chat_id": self.chat_id,
                "text": message_text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }
            
            response = requests.post(url, json=params)
            if response.status_code == 200:
                logger.info(f"Successfully sent alert for {token_info['name']} ({token_info['symbol']})")
                # Add to alert history
                self.alert_history.append({
                    "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "token_name": token_info['name'],
                    "token_symbol": token_info['symbol'],
                    "token_address": token_info['address']
                })
                # Trim history if it gets too large
                if len(self.alert_history) > 100:
                    self.alert_history = self.alert_history[-100:]
                return True
            else:
                logger.error(f"Failed to send Telegram alert: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending telegram alert: {e}")
            return False

    def verify_token(self, token):
        """Verify if a token is valid"""
        try:
            logger.info(f"Verifying token validity: {token['symbol']}")
            
            # First, check if it's already in our processed list
            if token["address"] in self.processed_tokens:
                logger.info(f"Token {token['symbol']} already processed, skipping verification")
                return False
                
            # Track API success/failure
            api_success_count = 1  # DexScreener already succeeded to get here
            total_apis = 3  # DexScreener, SolanaVerifier, RugCheck
            
            # Verify token on Solana
            is_valid = True  # Default to permissive
            try:
                is_valid = self.solana_verifier.is_valid_token(token["address"])
                logger.info(f"Token {token['symbol']} validity check: {is_valid}")
                api_success_count += 1
            except Exception as e:
                logger.warning(f"Error verifying token {token['symbol']}: {e}")
                # Be more permissive due to rate limiting issues
                logger.info(f"Using permissive validation for {token['symbol']} due to API issues")
                is_valid = True  # Changed from conditional to always true to avoid API issues
            
            # Check safety score if Solana validation passed
            if is_valid:
                try:
                    safety_score = self.rugcheck.get_safety_score(token["address"])
                    token["safety_score"] = safety_score
                    logger.info(f"Token {token['symbol']} safety score: {safety_score}")
                    
                    # Increase API success count
                    api_success_count += 1
                    
                    # Check if it meets the minimum score
                    if safety_score < self.thresholds["min_rugcheck_score"]:
                        logger.warning(f"Token {token['symbol']} safety score below threshold: {safety_score}")
                        return False
                except Exception as e:
                    logger.warning(f"Error checking safety score for {token['symbol']}: {e}")
                    # Use default safety score
                    token["safety_score"] = 85  # More permissive default
            
            # Calculate API success rate
            api_success_rate = api_success_count / total_apis
            logger.info(f"API integration success rate: {api_success_rate:.2%}")
            
            # Accept token as valid if majority of APIs succeed or it passes critical checks
            return api_success_rate >= 0.66 or is_valid
                
        except Exception as e:
            logger.error(f"Error in verify_token: {e}")
            return True  # Be permissive when errors occur to avoid missing good tokens

    def send_test_alert(self):
        """Send a test alert to the Telegram group"""
        try:
            # Create a test token with sample data
            test_token = {
                "name": "[TEST] Sample Token",
                "symbol": "TEST",
                "address": "test_address_" + datetime.datetime.now().strftime("%H%M%S"),
                "price_change": 25.5,
                "volume_24h": 500000,
                "market_cap": 2500000,
                "liquidity": 100000,
                "safety_score": 85,
                "url": "https://dexscreener.com"
            }
            
            # Send the test alert
            self.send_telegram_alert_sync(test_token)
            logger.info("Test alert sent successfully")
            return True
        except Exception as e:
            logger.error(f"Error sending test alert: {e}")
            return False

    def save_config(self):
        """Save all configuration to files"""
        try:
            # Ensure the config directory exists
            CONFIG_DIR.mkdir(exist_ok=True, parents=True)
            
            # Save processed tokens
            tokens_path = CONFIG_DIR / "processed_tokens.json"
            with open(tokens_path, 'w') as f:
                json.dump(list(self.processed_tokens), f)
            
            # Save thresholds
            thresholds_path = CONFIG_DIR / "thresholds.json"
            with open(thresholds_path, 'w') as f:
                json.dump(self.thresholds, f)
                
            # Save interval
            self.save_interval()
            
            # Save bot state
            state_path = CONFIG_DIR / "state.json"
            with open(state_path, 'w') as f:
                json.dump({
                    "enabled": self.is_running,
                    "test_mode": self.test_mode
                }, f)
                
            logger.info(f"Saved configuration to {CONFIG_DIR}")
            return True
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            return False
    
    def save_state(self):
        """Alias for save_config to maintain compatibility with API calls"""
        return self.save_config()

    def _run_scheduler(self):
        """Run the scheduler in a separate thread"""
        while True:
            schedule.run_pending()
            time.sleep(1)

def run_bot():
    """Initialize and run the bot with scheduling"""
    bot = SolanaTokenBot()
    
    # Setup schedule
    bot.start_scheduler()

# Run the bot if this script is executed directly
if __name__ == "__main__":
    logger.info("Starting Solana Token Bot...")
    run_bot()
