import asyncio
import telegram
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
import logging

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

class TelegramAlerter:
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.bot = None
        self._initialize_bot()

    def _initialize_bot(self):
        """Initialize the Telegram bot with the token"""
        if self.bot_token:
            self.bot = telegram.Bot(token=self.bot_token)
        else:
            logging.error("Telegram bot token not found in environment variables")

    async def send_message_async(self, message):
        """Send a message to the Telegram chat asynchronously"""
        if not self.bot or not self.chat_id:
            logging.error("Cannot send message: Bot not initialized or chat ID not set")
            return False

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=telegram.constants.ParseMode.MARKDOWN
            )
            return True
        except Exception as e:
            logging.error(f"Error sending Telegram message: {e}")
            return False

    def send_message(self, message):
        """Synchronous wrapper for sending a message"""
        return asyncio.run(self.send_message_async(message))

    def format_token_alert(self, token_info):
        """Format a token alert message"""
        # Get safety information if available
        safety_score = token_info.get('safety_score', 'N/A')
        safety_status = "✓ SAFE" if token_info.get('is_safe', False) else "⚠ CAUTION"
        safety_emoji = "🟢" if token_info.get('is_safe', False) else "🟠"
        
        # Get validation information if available
        is_valid = token_info.get('is_valid', 'N/A')
        valid_emoji = "✅" if is_valid else "❌" if is_valid is not True else "❓"
        
        # Format token address with short representation
        address = token_info.get('address', 'N/A')
        short_address = f"{address[:6]}...{address[-4:]}" if len(address) > 10 else address
        
        # Create message
        return (
            f"🚀 *New Solana Token Signal*\n\n"
            f"🔹 *Token*: {token_info['name']} ({token_info['symbol']})\n"
            f"🔹 *Contract*: `{short_address}`\n"
            f"🔹 *Market Cap*: ${token_info['market_cap']:,.2f}\n"
            f"🔹 *Volume (24h)*: ${token_info['volume_24h']:,.2f}\n"
            f"🔹 *Price Change*: {token_info['price_change']:+.2f}%\n"
            f"🔹 *Liquidity*: ${token_info['liquidity']:,.2f}\n" 
            f"🔹 *Buy/Sell Ratio*: {token_info['buy_sell_ratio']:.2f}\n"
            f"🔹 *Price*: ${token_info['price_usd']:,.8f}\n"
            f"{valid_emoji} *Valid Contract*: {is_valid}\n"
            f"{safety_emoji} *Safety Score*: {safety_score}/100 ({safety_status})\n"
            f"\n"
            f"[View Chart]({token_info['url']})"
        )

    def send_token_alert(self, token_info):
        """Send a formatted token alert to Telegram"""
        message = self.format_token_alert(token_info)
        return self.send_message(message)

# For testing
if __name__ == "__main__":
    alerter = TelegramAlerter()
    # Test with mock data
    test_token = {
        "name": "Test Token",
        "symbol": "TEST",
        "address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "market_cap": 1500000,
        "volume_24h": 450000,
        "price_change": 25.5,
        "liquidity": 250000,
        "buy_sell_ratio": 3.2,
        "url": "https://dexscreener.com/solana/test",
        "price_usd": 0.00001234,
        "safety_score": 85,
        "is_safe": True,
        "is_valid": True
    }
    alerter.send_token_alert(test_token)
