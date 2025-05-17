import os
import asyncio
from telegram import Bot

# Set the Telegram credentials directly for testing
TELEGRAM_BOT_TOKEN = "8127502962:AAHP9nfYJNyoQplbAuNcRsbQNSDKBrsQ5j8"
TELEGRAM_CHAT_ID = "-1002457519323"

async def test_telegram_api():
    """
    Test sending a message to Telegram
    """
    print(f"Testing Telegram API with token: {TELEGRAM_BOT_TOKEN[:8]}...")
    
    try:
        # Initialize the bot
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        
        # Get bot info to verify connection
        bot_info = await bot.get_me()
        print(f"Connected to bot: {bot_info.first_name} (@{bot_info.username})")
        
        # Send a test message
        message = (
            "🧪 *API Test Message*\n\n"
            "This is a test message from the Solana Token Bot.\n"
            "If you're seeing this, the Telegram API is working correctly!\n\n"
            "✅ Connection successful"
        )
        
        sent_message = await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode="Markdown"
        )
        
        print(f"Message sent successfully! Message ID: {sent_message.message_id}")
        return True
    except Exception as e:
        print(f"Error sending Telegram message: {e}")
        return False

if __name__ == "__main__":
    # Run the async test
    success = asyncio.run(test_telegram_api())
    
    if success:
        print("✅ Telegram API test passed!")
    else:
        print("❌ Telegram API test failed!") 