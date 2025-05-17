import asyncio
import sys
import logging
from bot import SolanaTokenBot
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Test data for a token alert
TEST_TOKEN = {
    "name": "[TEST] AsyncIO Fix Test Token",
    "symbol": "TEST",
    "address": "HW7Ku9ULKKKTcHeVZyymZVqeZnGN1JbGLKKdMznVD4ew", # Random Solana address for testing
    "market_cap": 1000000.0,
    "volume_24h": 500000.0,
    "price_change": 25.5,
    "liquidity": 250000.0,
    "buy_sell_ratio": 1.5,
    "url": "https://dexscreener.com/solana/test",
    "price_usd": 0.00001234
}

async def test_send_message():
    """Test sending a Telegram message in an async context (simulating FastAPI)"""
    logger.info("Starting async Telegram message test...")
    
    # Initialize bot
    token_bot = SolanaTokenBot()
    
    # Send a plain text message
    logger.info("Testing send_plain_telegram_message...")
    success = await token_bot.send_plain_telegram_message(
        "🧪 *AsyncIO Fix Test* - Testing that sending messages from a FastAPI endpoint works properly."
    )
    
    if success:
        logger.info("✅ Plain telegram message sent successfully!")
    else:
        logger.error("❌ Failed to send plain telegram message")
        return False
    
    # Add a small delay
    await asyncio.sleep(1)
    
    # Test sending a token alert (the function that was failing)
    logger.info("Testing send_telegram_alert...")
    success = await token_bot.send_telegram_alert(TEST_TOKEN)
    
    if success:
        logger.info("✅ Token alert telegram message sent successfully!")
        return True
    else:
        logger.error("❌ Failed to send token alert")
        return False

async def test_find_specific_token():
    """Test the find_specific_token method that was failing"""
    logger.info("Testing find_specific_token method...")
    
    # Initialize bot
    token_bot = SolanaTokenBot()
    token_bot.test_mode = True  # Enable test mode
    token_bot.force_verification = True
    
    # Test with a known Solana token
    WIF_TOKEN_ADDRESS = "5tN42n9vMi6ubp67Uy4NnmM5DMZYN8aS8GeB3bEDHr6E"  # WiFi token address
    
    # Simulate the FastAPI endpoint
    logger.info(f"Testing find_specific_token with {WIF_TOKEN_ADDRESS}...")
    result = token_bot.find_specific_token(WIF_TOKEN_ADDRESS)
    
    if result:
        logger.info("✅ find_specific_token method works successfully!")
        return True
    else:
        logger.error("❌ Failed to find and alert about specific token")
        return False

async def run_tests():
    """Run all tests"""
    results = []
    
    # Test sending a message
    msg_result = await test_send_message()
    results.append(("Send Telegram Message", msg_result))
    
    # Add a small delay
    await asyncio.sleep(2)
    
    # Test finding a specific token
    token_result = await test_find_specific_token()
    results.append(("Find Specific Token", token_result))
    
    # Print results
    logger.info("\n===== TEST RESULTS =====")
    all_passed = True
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{test_name}: {status}")
        if not result:
            all_passed = False
    
    return all_passed

if __name__ == "__main__":
    logger.info("Running asyncio fix tests...")
    result = asyncio.run(run_tests())
    sys.exit(0 if result else 1) 