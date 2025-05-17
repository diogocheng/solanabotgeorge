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
    THRESHOLDS
)

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
        self.thresholds = THRESHOLDS
        self.processed_tokens = set()  # Instance variable
        self.last_run_time = None
        self.is_running = BOT_ENABLED  # This now uses the persisted state from config.py
        self.alert_history = []  # Store alert history for API
        self._schedule_started = False
        self.check_interval = CHECK_INTERVAL_MINUTES
        self.job = None  # Store the scheduled job for rescheduling
        
        # For debugging/testing
        self.test_mode = False
        self.force_verification = False
        
        logger.info(f"Bot initialized with state: {'ENABLED' if self.is_running else 'DISABLED'}")
        logger.info(f"Check interval set to {self.check_interval} minutes")
        
    async def send_telegram_alert(self, token_info):
        """Send alert about token to Telegram"""
        try:
            # Format token information for the alert
            safety_score = self.rugcheck.get_safety_score(token_info["address"])
            
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
                
            # Send message
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
            
            for token in tokens:
                # Skip already processed tokens
                if token["address"] in self.processed_tokens:
                    logger.info(f"Skipping already processed token: {token['symbol']} ({token['address']})")
                    continue
                
                logger.info(f"Processing potential token: {token['name']} ({token['symbol']}) - {token['address']}")
                
                # Verify token on Solana (with enhanced error handling)
                is_valid = False
                try:
                    is_valid = self.solana_verifier.is_valid_token(token["address"])
                    logger.info(f"Token {token['symbol']} validity check: {is_valid}")
                except Exception as e:
                    logger.warning(f"Error verifying token {token['symbol']}: {e}")
                    # Be more permissive due to rate limiting issues
                    is_valid = self.force_verification or True
                
                # Store verification status in token info
                token["is_valid"] = is_valid
                
                # Check safety score with enhanced logging
                try:
                    safety_score = self.rugcheck.get_safety_score(token["address"])
                    logger.info(f"Token {token['symbol']} safety score: {safety_score}")
                    is_safe = safety_score >= self.thresholds["min_rugcheck_score"]
                except Exception as e:
                    logger.warning(f"Error getting safety score for {token['symbol']}: {e}")
                    # Use a default safety score if we couldn't check
                    safety_score = 70
                    is_safe = self.force_verification or True
                
                # Process token if it passes all checks
                if is_valid and (is_safe or self.force_verification):
                    logger.info(f"✨ New valid token found: {token['name']} ({token['symbol']})")
                    
                    # Add more token details for better alerts
                    if 'price_usd' not in token or token['price_usd'] == 0:
                        # Try to fetch more details if needed
                        pair_info = self.dexscreener.get_token_pair_by_address(token["address"])
                        if pair_info and 'priceUsd' in pair_info:
                            token['price_usd'] = pair_info['priceUsd']
                    
                    # Send alert asynchronously - use create_task if in an event loop
                    try:
                        # Create a new event loop if there isn't one
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                # We're in an existing event loop, use create_task
                                asyncio.create_task(self.send_telegram_alert(token))
                            else:
                                # No running event loop, use run_until_complete
                                loop.run_until_complete(self.send_telegram_alert(token))
                        except RuntimeError:
                            # No event loop, create one
                            asyncio.run(self.send_telegram_alert(token))
                            
                        new_tokens += 1
                        self.processed_tokens.add(token["address"])
                    except Exception as e:
                        logger.error(f"Failed to send alert for {token['symbol']}: {e}")
                else:
                    reasons = []
                    if not is_valid:
                        reasons.append("invalid token")
                    if not is_safe:
                        reasons.append(f"safety score too low ({safety_score})")
                    
                    logger.info(f"Skipping token {token['symbol']}: {', '.join(reasons)}")
            
            logger.info(f"Scan complete. Sent {new_tokens} new token alerts.")
            
            # If no tokens were found but we're in test mode, send a test alert
            if new_tokens == 0 and self.test_mode and tokens:
                logger.info("Test mode: Sending test alert for the first matching token")
                # Use the first token that matched filters but send as a test
                test_token = tokens[0]
                test_token["name"] = f"[TEST] {test_token['name']}"
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # We're in an existing event loop, use create_task
                        asyncio.create_task(self.send_telegram_alert(test_token))
                    else:
                        # No running event loop, use run_until_complete
                        loop.run_until_complete(self.send_telegram_alert(test_token))
                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(self.send_telegram_alert(test_token))
            
        except Exception as e:
            logger.error(f"Error during token scan: {e}")
            import traceback
            logger.error(f"Scan error details: {traceback.format_exc()}")
    
    def update_check_interval(self, minutes):
        """Update the check interval and reschedule the job"""
        if minutes < 1:
            logger.warning(f"Invalid check interval: {minutes}. Must be at least 1 minute.")
            return False
            
        logger.info(f"Updating check interval from {self.check_interval} to {minutes} minutes")
        self.check_interval = minutes
        
        # Reschedule if already running
        if self.job:
            schedule.cancel_job(self.job)
            self.job = schedule.every(self.check_interval).minutes.do(self.run_scheduled_task)
            logger.info(f"Rescheduled job to run every {self.check_interval} minutes")
            
        return True
        
    def run_scheduled_task(self):
        """Run the scheduled token scan if bot is enabled"""
        if self.is_running:
            logger.info(f"Running scheduled token scan (interval: {self.check_interval} minutes)...")
            self.scan_for_tokens()
        else:
            logger.info("Bot is disabled, skipping scheduled scan")

    def run(self):
        if self._schedule_started:
            return  # Prevent multiple schedules
        self._schedule_started = True
        self.job = schedule.every(self.check_interval).minutes.do(self.run_scheduled_task)
        if self.is_running:
            logger.info("Performing initial token scan...")
            self.scan_for_tokens()
        logger.info(f"Bot started, checking every {self.check_interval} minutes")
        while True:
            schedule.run_pending()
            time.sleep(1)

    def check_tokens(self):
        """Trigger an immediate token check"""
        logger.info("Manual token check triggered")
        self.scan_for_tokens()
        
    def find_specific_token(self, token_address):
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
                
            token_info = {
                "name": base_token.get("name", "Unknown"),
                "symbol": base_token.get("symbol", "Unknown"),
                "address": token_address,
                "market_cap": float(pair_info.get("fdv", 0) or 0),
                "volume_24h": float(pair_info.get("volume", {}).get("h24", 0) or 0),
                "price_change": float(str(pair_info.get("priceChange", {}).get("h24", "0")).replace("%", "") or 0),
                "liquidity": float(pair_info.get("liquidity", {}).get("usd", 0) or 0),
                "buy_sell_ratio": 1.0,  # Default
                "url": pair_info.get("url", f"https://dexscreener.com/solana/{token_address}"),
                "price_usd": pair_info.get("priceUsd", 0)
            }
            
            # Try to get buy/sell ratio
            if "txns" in pair_info and "h24" in pair_info["txns"]:
                buys = int(pair_info["txns"]["h24"].get("buys", 0) or 0)
                sells = int(pair_info["txns"]["h24"].get("sells", 0) or 0)
                token_info["buy_sell_ratio"] = buys / max(sells, 1)
                
            # Force verification for specific token checks
            is_valid = self.solana_verifier.is_valid_token(token_address)
            logger.info(f"Specific token validity: {is_valid}")
            
            # Add verification status to token info
            token_info["is_valid"] = is_valid
            
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
            return True
            
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

def run_bot():
    """Initialize and run the bot with scheduling"""
    bot = SolanaTokenBot()
    
    # Setup schedule
    bot.run()

# Run the bot if this script is executed directly
if __name__ == "__main__":
    logger.info("Starting Solana Token Bot...")
    run_bot() 