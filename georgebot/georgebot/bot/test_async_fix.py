import asyncio
import sys
import logging
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

# Apply the fix directly to bot.py without restarting the container
def apply_fixes():
    """Apply fixes to bot.py directly in the container"""
    import bot
    from bot import SolanaTokenBot
    
    # Patch find_specific_token method
    original_find_specific_token = SolanaTokenBot.find_specific_token
    
    # Create patched version
    def patched_find_specific_token(self, token_address):
        """Patched version of find_specific_token"""
        logger.info(f"PATCHED find_specific_token for: {token_address}")
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
            
            # Always send an alert for specific token checks - handle asyncio properly
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're in an existing event loop, use create_task
                    logger.info("Using create_task in running event loop")
                    asyncio.create_task(self.send_telegram_alert(token_info))
                else:
                    # No running event loop, use run_until_complete
                    logger.info("Using run_until_complete in existing event loop")
                    loop.run_until_complete(self.send_telegram_alert(token_info))
            except RuntimeError:
                # No event loop, create one
                logger.info("Creating new event loop with asyncio.run")
                asyncio.run(self.send_telegram_alert(token_info))
                
            self.processed_tokens.add(token_address)
            return True
            
        except Exception as e:
            logger.error(f"Error finding specific token {token_address}: {e}")
            import traceback
            logger.error(f"Find token error: {traceback.format_exc()}")
            return False
    
    # Apply the patch
    logger.info("Applying patch to SolanaTokenBot.find_specific_token...")
    SolanaTokenBot.find_specific_token = patched_find_specific_token
    
    return "Fixes applied to bot.py"

async def test_find_specific_token():
    """Test the patched find_specific_token method"""
    from bot import SolanaTokenBot
    logger.info("Testing patched find_specific_token method...")
    
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
    """Apply patches and run all tests"""
    results = []
    
    # Apply fixes first
    result = apply_fixes()
    logger.info(f"Patch result: {result}")
    
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
    logger.info("Running asyncio fix tests with monkey-patching...")
    result = asyncio.run(run_tests())
    sys.exit(0 if result else 1) 