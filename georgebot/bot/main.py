import os
import json
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
import logging
from datetime import datetime
from bot import TokenBot
import asyncio
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

logger = logging.getLogger(__name__)
bot = TokenBot()

# Create FastAPI app
app = FastAPI()

@app.get("/")
def read_root():
    """Root endpoint"""
    return {"status": "Solana Token Bot is running"}

@app.get("/status")
def get_status():
    """Get bot status"""
    return {
        "enabled": bot.is_running,
        "last_run": bot.last_run_time.strftime("%Y-%m-%d %H:%M:%S") if bot.last_run_time else None,
        "total_tokens_processed": len(bot.processed_tokens),
        "check_interval_minutes": bot.check_interval
    }

@app.post("/enable")
def enable_bot():
    """Enable the bot"""
    if bot.is_running:
        return {"status": "Bot is already enabled"}
    bot.enable()
    return {"status": "Bot enabled"}

@app.post("/disable")
def disable_bot():
    """Disable the bot"""
    if not bot.is_running:
        return {"status": "Bot is already disabled"}
    bot.disable()
    return {"status": "Bot disabled"}

@app.post("/run-now")
def run_scan():
    """Run a scan immediately"""
    bot.scan_for_tokens()
    return {"status": "Scan completed"}

@app.post("/test-alert")
def send_test_alert():
    """Send a test alert to Telegram"""
    bot.send_test_alert()
    return {"status": "Test alert sent"}

@app.get("/thresholds")
def get_thresholds():
    """Get current threshold values"""
    return bot.thresholds

@app.post("/thresholds")
def update_thresholds(thresholds: Dict):
    """Update threshold values"""
    if not bot.update_thresholds(thresholds):
        raise HTTPException(status_code=400, detail="Invalid threshold format")
    return {"status": "Thresholds updated", "new_thresholds": bot.thresholds}

@app.post("/test-mode/{enabled}")
def set_test_mode(enabled: bool):
    """Enable/disable test mode"""
    bot.test_mode = enabled
    return {"status": f"Test mode {'enabled' if enabled else 'disabled'}"}

@app.post("/reset-processed-tokens")
def reset_processed_tokens():
    """Reset the list of processed tokens"""
    bot.processed_tokens = set()
    bot.save_config()  # Make sure changes are persisted
    return {"status": "Processed tokens list cleared", "count": 0}

@app.post("/check-interval/{minutes}")
def update_check_interval(minutes: int):
    """Update the bot's check interval (in minutes)"""
    if minutes < 1 or minutes > 60:
        raise HTTPException(status_code=400, detail="Interval must be between 1 and 60 minutes")
        
    success = bot.update_check_interval(minutes)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update check interval")
        
    # Send notification about the change
    asyncio.create_task(bot.send_status_message(f"⚙️ The Solana Token Bot check interval has been updated to {minutes} minutes"))
    
    return {
        "status": "Check interval updated",
        "check_interval_minutes": minutes
    }

@app.get("/alerts")
def get_alerts(limit: int = 10):
    """Get recent alerts"""
    return {"alerts": bot.alert_history[-limit:] if bot.alert_history else []}

@app.post("/token/{token_address}")
def process_specific_token(token_address: str):
    """Process a specific token by address"""
    result = bot.process_specific_token(token_address)
    if result:
        return {"status": "success", "processed": True}
    else:
        return {"status": "error", "processed": False}

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

if __name__ == "__main__":
    # Start the bot
    bot.run()
    
    # Start the API
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False) 