from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel
import json
from typing import Dict, Any, List, Optional
from pathlib import Path
import threading
import concurrent.futures
from bot import SolanaTokenBot
from config import load_thresholds, save_thresholds, load_check_interval, save_check_interval, CHECK_INTERVAL_MINUTES, THRESHOLDS, TELEGRAM_CHAT_ID, save_bot_status
import datetime
import asyncio

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
    check_interval: int
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
        bot_thread = threading.Thread(target=token_bot.run, daemon=True)
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
        "check_interval": token_bot.check_interval,
        "thresholds": token_bot.thresholds
    }

@app.post("/toggle", tags=["Bot Control"])
async def toggle_bot(enable: bool):
    """Enable or disable the bot"""
    global bot_thread
    if enable:
        token_bot.is_running = True
        if bot_thread is None or not bot_thread.is_alive():
            bot_thread = threading.Thread(target=token_bot.run, daemon=True)
            bot_thread.start()
        # Save status to config file
        print(f"Trying to save bot status to file: {enable}")
        success = save_bot_status(True)
        print(f"Save result: {success}")
        # Send Telegram message directly with await since we're in an async function
        await token_bot.send_plain_telegram_message("✅ The Solana Token Bot has been *ENABLED* and is now running.")
    else:
        token_bot.is_running = False
        # Save status to config file
        print(f"Trying to save bot status to file: {enable}")
        success = save_bot_status(False)
        print(f"Save result: {success}")
        # Send Telegram message directly with await since we're in an async function
        await token_bot.send_plain_telegram_message("⏹️ The Solana Token Bot has been *DISABLED* and is now stopped.")
    return {"status": "success", "enabled": token_bot.is_running}

@app.get("/thresholds", tags=["Configuration"])
async def get_thresholds():
    """Get the current filter thresholds"""
    return THRESHOLDS

@app.post("/thresholds", tags=["Configuration"])
async def update_thresholds(update: ThresholdUpdate):
    """Update the filter thresholds"""
    current_thresholds = load_thresholds()
    
    # Update only provided values
    for key, value in update.dict(exclude_unset=True).items():
        if value is not None:
            current_thresholds[key] = value
    
    # Save updated thresholds
    if save_thresholds(current_thresholds):
        # Update the bot's thresholds
        token_bot.thresholds = current_thresholds
        # Send Telegram message directly with await
        await token_bot.send_plain_telegram_message("⚙️ The Solana Token Bot filter thresholds have been *updated* and saved.")
        return {"status": "success", "thresholds": current_thresholds}
    else:
        raise HTTPException(status_code=500, detail="Failed to save thresholds")

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
        threading.Thread(target=token_bot.run, daemon=True).start()
        
        # Send a startup notification to Telegram
        system_info = {
            "timestamp": datetime.datetime.now().isoformat(),
            "enabled": token_bot.is_running,
            "check_interval": f"{token_bot.check_interval} minutes",
            "thresholds": token_bot.thresholds
        }
        
        startup_message = (
            f"🚀 *Solana Token Bot System Started*\n\n"
            f"🕒 *Time*: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"⚙️ *Status*: {'ENABLED' if token_bot.is_running else 'DISABLED'}\n"
            f"🔍 *Check Interval*: Every {token_bot.check_interval} minutes\n\n"
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
            # Add verification status to token info
            token_info["is_valid"] = is_valid
        except Exception as e:
            print(f"Error verifying token: {e}")
            is_valid = True  # Be permissive for API endpoints
            token_info["is_valid"] = is_valid
            
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

@app.get("/check-interval", tags=["Configuration"])
async def get_check_interval():
    """Get the current check interval in minutes"""
    return {"check_interval": token_bot.check_interval}

@app.post("/check-interval/{minutes}", tags=["Configuration"])
async def set_check_interval(minutes: int):
    """Set the check interval in minutes (minimum 1 minute)"""
    if minutes < 1:
        raise HTTPException(status_code=400, detail="Check interval must be at least 1 minute")
    
    # Update the bot's check interval
    success = token_bot.update_check_interval(minutes)
    
    # Save the new interval to configuration
    if success:
        config_success = save_check_interval(minutes)
        
        # Send notification to Telegram
        notification = (
            f"⏱️ *Check Interval Updated*\n\n"
            f"The token scan interval has been changed to *{minutes} minute{'s' if minutes > 1 else ''}*.\n\n"
            f"_New scans will run at this interval going forward._"
        )
        
        await token_bot.send_plain_telegram_message(notification)
        
        return {
            "status": "success", 
            "check_interval": minutes,
            "config_saved": config_success
        }
    else:
        raise HTTPException(status_code=400, detail="Failed to update check interval")

def start_api():
    """Start the FastAPI server"""
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    start_api() 