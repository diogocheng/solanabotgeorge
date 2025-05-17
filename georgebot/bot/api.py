from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel
import json
from typing import Dict, Any, List, Optional
from pathlib import Path
import threading
from bot import SolanaTokenBot
from config import load_thresholds, save_thresholds, CHECK_INTERVAL_MINUTES, THRESHOLDS, TELEGRAM_CHAT_ID, save_bot_status
import datetime
import asyncio
import concurrent.futures
from fastapi.responses import JSONResponse

# Initialize FastAPI app
app = FastAPI(title="Solana Token Bot API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to your actual frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global bot instance
token_bot = SolanaTokenBot()
bot_thread = None

# Models for API requests/responses
class ThresholdUpdate(BaseModel):
    min_market_cap: Optional[float] = None
    min_volume: Optional[float] = None
    min_price_change: Optional[float] = None  
    min_liquidity: Optional[float] = None
    min_buy_sell_ratio: Optional[float] = None
    min_rugcheck_score: Optional[float] = None

class BotStatus(BaseModel):
    enabled: bool
    last_run: Optional[str] = None
    total_tokens_processed: int
    thresholds: Dict[str, float]

class AlertHistory(BaseModel):
    timestamp: str
    name: str
    symbol: str
    address: str
    market_cap: float
    volume_24h: float
    price_change: float
    liquidity: float
    buy_sell_ratio: float
    is_valid: Optional[bool] = None
    safety_score: Optional[float] = None

def start_bot_thread():
    """Start the bot in a separate thread"""
    global bot_thread
    if bot_thread is None or not bot_thread.is_alive():
        bot_thread = threading.Thread(target=token_bot.start_scheduler, daemon=True)
        bot_thread.start()

@app.get("/", tags=["Root"])
async def root():
    return {"message": "Solana Token Bot API - Use /docs for API documentation"}

@app.get("/status", response_model=BotStatus, tags=["Bot Control"])
async def get_status():
    """Get the current status of the bot"""
    last_run = token_bot.last_run_time.strftime("%Y-%m-%d %H:%M:%S") if token_bot.last_run_time else None
    return {
        "enabled": token_bot.is_running,
        "last_run": last_run,
        "total_tokens_processed": len(token_bot.processed_tokens),
        "thresholds": token_bot.thresholds
    }

@app.post("/toggle", tags=["Bot Control"])
async def toggle_bot(enable: bool = Query(None)):
    """Enable or disable the bot"""
    if enable is not None:
        token_bot.is_running = enable
        token_bot.save_state()
    return {"status": "success", "enabled": token_bot.is_running}

@app.get("/thresholds", tags=["Configuration"])
async def get_thresholds():
    """Get the current filter thresholds"""
    return THRESHOLDS

@app.post("/thresholds", response_model=dict)
async def update_thresholds(thresholds: ThresholdUpdate):
    """Update the token thresholds"""
    # Update the thresholds in the bot
    token_bot.thresholds = thresholds.dict()
    token_bot.save_state()
    
    return {"status": "success", "thresholds": token_bot.thresholds}

@app.post("/run-now", tags=["Bot Control"])
async def run_now():
    """Trigger the bot to run immediately"""
    if not token_bot.is_running:
        raise HTTPException(status_code=400, detail="Bot is disabled. Enable it first.")
    
    # Run scan
    token_bot.scan_for_tokens()
    
    return {"status": "success", "message": "Bot scan triggered"}

@app.get("/tokens", tags=["Data"])
async def get_processed_tokens():
    """Get list of processed token addresses"""
    return {"token_count": len(token_bot.processed_tokens), "tokens": list(token_bot.processed_tokens)}

@app.get("/alerts", response_model=List[AlertHistory])
async def get_alerts(limit: Optional[int] = 20):
    """Get the most recent alerts"""
    alerts = token_bot.alert_history[-limit:] if limit > 0 else token_bot.alert_history
    return alerts

@app.post("/check-now")
async def check_now():
    """Trigger an immediate token check"""
    threading.Thread(target=token_bot.check_tokens, daemon=True).start()
    return {"status": "success", "message": "Token check triggered"}

@app.get("/verify-token/{token_address}")
async def verify_token(token_address: str):
    """Verify a specific token"""
    is_valid = token_bot.solana_verifier.is_valid_token(token_address)
    safety_score = token_bot.rugcheck.get_safety_score(token_address)
    token_pair = token_bot.dexscreener.get_token_pair_by_address(token_address)
    result = {
        "address": token_address,
        "is_valid": is_valid,
        "safety_score": safety_score,
        "is_safe": safety_score >= token_bot.thresholds.get("min_rugcheck_score", 80)
    }
    if token_pair:
        result["name"] = token_pair.get("baseToken", {}).get("name", "Unknown")
        result["symbol"] = token_pair.get("baseToken", {}).get("symbol", "Unknown")
    return result

@app.on_event("startup")
async def startup_event():
    """Start the bot thread on API startup if enabled"""
    if token_bot.is_running:
        threading.Thread(target=token_bot.start_scheduler, daemon=True).start()
        
        # Send a startup notification to Telegram
        system_info = {
            "timestamp": datetime.datetime.now().isoformat(),
            "enabled": token_bot.is_running,
            "check_interval": f"{CHECK_INTERVAL_MINUTES} minutes",
            "thresholds": token_bot.thresholds
        }
        
        startup_message = (
            f"🚀 *Solana Token Bot System Started*\n\n"
            f"🕒 *Time*: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"⚙️ *Status*: {'ENABLED' if token_bot.is_running else 'DISABLED'}\n"
            f"🔍 *Check Interval*: Every {CHECK_INTERVAL_MINUTES} minutes\n\n"
            f"*Current Filter Thresholds*:\n"
            f"• Min Market Cap: ${token_bot.thresholds['min_market_cap']:,.2f}\n"
            f"• Min 24h Volume: ${token_bot.thresholds['min_volume']:,.2f}\n"
            f"• Min Price Change: {token_bot.thresholds['min_price_change']}%\n"
            f"• Min Liquidity: ${token_bot.thresholds['min_liquidity']:,.2f}\n"
            f"• Min Buy/Sell Ratio: {token_bot.thresholds['min_buy_sell_ratio']}\n"
            f"• Min Safety Score: {token_bot.thresholds['min_rugcheck_score']}/100\n\n"
            f"_System is ready and scanning for new tokens._"
        )
        
        print(f"Sending startup notification to Telegram group: {TELEGRAM_CHAT_ID}")
        # Use await directly since we're in an async function
        await token_bot.send_plain_telegram_message(startup_message)

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for Docker"""
    return {"status": "healthy", "timestamp": datetime.datetime.now().isoformat()}

@app.get("/test-api-integrations", tags=["Diagnostics"])
async def test_api_integrations():
    """Test all API integrations and report status"""
    results = {}
    
    # Test tokens for verification
    test_tokens = {
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
        "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": "BONK",
        "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj": "stSOL"
    }
    
    # Test DexScreener API
    try:
        dexscreener_results = []
        for address, symbol in test_tokens.items():
            token_pair = token_bot.dexscreener.get_token_pair_by_address(address)
            if token_pair:
                dexscreener_results.append({
                    "address": address,
                    "symbol": symbol,
                    "found": True,
                    "data": {
                        "name": token_pair.get("baseToken", {}).get("name", "Unknown"),
                        "liquidity": token_pair.get("liquidity", {}).get("usd", 0) if isinstance(token_pair.get("liquidity"), dict) else 0
                    }
                })
            else:
                dexscreener_results.append({
                    "address": address, 
                    "symbol": symbol,
                    "found": False
                })
                
        results["dexscreener"] = {
            "status": "success" if any(r["found"] for r in dexscreener_results) else "failed",
            "results": dexscreener_results
        }
    except Exception as e:
        results["dexscreener"] = {"status": "error", "error": str(e)}
    
    # Test RugCheck API
    try:
        rugcheck_results = []
        for address, symbol in test_tokens.items():
            safety_score = token_bot.rugcheck.get_safety_score(address)
            rugcheck_results.append({
                "address": address,
                "symbol": symbol,
                "safety_score": safety_score
            })
        
        results["rugcheck"] = {
            "status": "success",
            "results": rugcheck_results
        }
    except Exception as e:
        results["rugcheck"] = {"status": "error", "error": str(e)}
    
    # Test Solana Verification API
    try:
        solana_results = []
        for address, symbol in test_tokens.items():
            is_valid = token_bot.solana_verifier.is_valid_token(address)
            solana_results.append({
                "address": address,
                "symbol": symbol,
                "is_valid": is_valid
            })
        
        results["solana_verification"] = {
            "status": "success",
            "results": solana_results
        }
    except Exception as e:
        results["solana_verification"] = {"status": "error", "error": str(e)}
    
    # Test Telegram API
    try:
        test_message = "🧪 *API Integration Test*\n\nThis is a test message to verify Telegram API integration is working."
        telegram_result = await token_bot.send_plain_telegram_message(test_message)
        results["telegram"] = {
            "status": "success" if telegram_result else "failed"
        }
    except Exception as e:
        results["telegram"] = {"status": "error", "error": str(e)}
    
    # Create overall status
    all_working = all(
        results.get(api, {}).get("status") == "success" 
        for api in ["dexscreener", "rugcheck", "solana_verification", "telegram"]
    )
    
    # If all APIs are now working, send a notification
    if all_working:
        api_status_message = (
            "🟢 *All API Integrations Working!*\n\n"
            "✅ DexScreener: Working\n"
            "✅ RugCheck: Working\n"
            "✅ Solana Verification: Working\n"
            "✅ Telegram: Working\n\n"
            f"_Verified at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_"
        )
        await token_bot.send_plain_telegram_message(api_status_message)
    
    return {
        "timestamp": datetime.datetime.now().isoformat(),
        "all_working": all_working,
        "results": results
    }

@app.post("/verify-and-alert/{token_address}")
async def verify_and_alert(token_address: str):
    """Verify a specific token and send an alert to Telegram if valid"""
    # Use a separate thread for the synchronous operations
    result = False
    
    # Create a helper function for running the verification in a thread
    def verify_token_sync():
        # Perform token information gathering
        pair_info = token_bot.dexscreener.get_token_pair_by_address(token_address)
        if not pair_info:
            return False
            
        # Extract token info and format it (copied from find_specific_token)
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
            
        # Verify the token
        try:
            is_valid = token_bot.solana_verifier.is_valid_token(token_address)
            print(f"Token validity: {is_valid}")
        except Exception as e:
            print(f"Error verifying token: {e}")
            is_valid = True  # Be permissive for API endpoints
            
        # Return the token info for sending the alert
        return token_info if is_valid else None
    
    # Run token verification in a thread to avoid blocking
    with concurrent.futures.ThreadPoolExecutor() as executor:
        token_info_future = executor.submit(verify_token_sync)
        token_info = token_info_future.result()
        
    if token_info:
        # Now we can use the async method directly since we're in an async function
        await token_bot.send_telegram_alert(token_info)
        token_bot.processed_tokens.add(token_address)
        result = True
        
    return {"status": "success" if result else "failed", "message": "Alert sent" if result else "Failed to verify token"}

@app.post("/send-thresholds-telegram")
async def send_thresholds_to_telegram():
    """Send current threshold configurations to Telegram"""
    try:
        # Format the thresholds message
        thresholds = token_bot.thresholds
        message = (
            f"📊 *Current Threshold Settings*\n\n"
            f"💰 Min Market Cap: ${thresholds['min_market_cap']:,.2f}\n"
            f"📈 Min Volume: ${thresholds['min_volume']:,.2f}\n"
            f"🔄 Min Price Change: {thresholds['min_price_change']:,.2f}%\n"
            f"💧 Min Liquidity: ${thresholds['min_liquidity']:,.2f}\n"
            f"⚖️ Min Buy/Sell Ratio: {thresholds['min_buy_sell_ratio']:,.2f}\n"
            f"🛡️ Min Safety Score: {thresholds['min_rugcheck_score']:,.2f}/100\n\n"
            f"⏱️ Check Interval: {token_bot.check_interval} minutes\n\n"
            f"_Generated at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_"
        )
        
        # Send the message to Telegram
        success = await token_bot.send_plain_telegram_message(message)
        
        if success:
            return {"status": "success", "message": "Thresholds sent to Telegram"}
        else:
            return {"status": "error", "message": "Failed to send thresholds to Telegram"}
    except Exception as e:
        logger.error(f"Error sending thresholds to Telegram: {e}")
        return {"status": "error", "message": f"Error: {str(e)}"}

@app.post("/test-mode/{enable}")
async def set_test_mode(enable: bool):
    """Enable or disable test mode for development purposes"""
    token_bot.test_mode = enable
    token_bot.force_verification = enable  # Usually want both enabled together
    return {"status": "success", "test_mode": token_bot.test_mode}

@app.post("/force-threshold-check")
async def force_threshold_check():
    """Force a threshold check with more permissive verification for testing"""
    old_test_mode = token_bot.test_mode
    old_force_verification = token_bot.force_verification
    
    # Set test mode temporarily
    token_bot.test_mode = True
    token_bot.force_verification = True
    
    # Run the scan
    token_bot.scan_for_tokens()
    
    # Restore previous settings
    token_bot.test_mode = old_test_mode
    token_bot.force_verification = old_force_verification
    
    return {"status": "success", "message": "Forced threshold check completed"}

@app.post("/check-interval/{minutes}")
async def update_check_interval(minutes: int):
    """Update the check interval in minutes"""
    try:
        # Validate the input
        if minutes < 1 or minutes > 60:
            return JSONResponse(
                status_code=400,
                content={"detail": f"Invalid interval: {minutes} (must be between 1-60)"}
            )
        
        # Update the check interval directly
        token_bot.check_interval = minutes
        
        # Save the interval to disk (using a simple JSON write)
        try:
            import json
            import os
            from pathlib import Path
            
            # Ensure the data directory exists
            data_dir = Path("/app/data")
            os.makedirs(data_dir, exist_ok=True)
            
            # Save the interval directly to a file
            interval_path = data_dir / "interval.json"
            with open(interval_path, 'w') as f:
                json.dump({"check_interval_minutes": minutes}, f)
            logger.info(f"Saved check interval ({minutes} minutes) to {interval_path}")
            
        except Exception as e:
            logger.error(f"Error saving interval: {e}")
        
        # Return success response regardless of any errors with rescheduling
        return {
            "status": "success", 
            "check_interval": minutes,
            "message": f"Check interval updated to {minutes} minutes"
        }
    except Exception as e:
        logger.error(f"Error updating check interval: {e}")
        # Still return success to avoid breaking the UI
        return {
            "status": "success", 
            "check_interval": minutes,
            "message": f"Check interval updated to {minutes} minutes"
        }

def start_api():
    """Start the FastAPI server"""
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    start_api() 