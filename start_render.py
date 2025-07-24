#!/usr/bin/env python3
"""
Render.com startup script for BingX Trading Bot
Runs both the web API server and the trading bot in the same process
"""

import asyncio
import os
import sys
import logging
import uvicorn
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from api.web_api import app
from main import TradingBot


async def start_trading_bot():
    """Start the trading bot in the background"""
    try:
        bot = TradingBot()
        await bot.initialize()
        await bot.start()
        
        # Keep the bot running
        while bot.is_running:
            await asyncio.sleep(1)
            
    except Exception as e:
        logging.error(f"Error starting trading bot: {e}")


def main():
    """Main entry point for Render deployment"""
    try:
        # Setup logging
        logging.basicConfig(
            level=getattr(logging, Settings.LOG_LEVEL.upper(), logging.INFO),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Get port from environment (Render sets this)
        port = int(os.getenv("PORT", "8000"))
        
        # Create logs directory
        os.makedirs("logs", exist_ok=True)
        
        print(f"🚀 Starting BingX Trading Bot on port {port}")
        print(f"📊 Environment: {Settings.ENVIRONMENT}")
        print(f"🔧 Debug mode: {Settings.DEBUG}")
        
        # Start the trading bot as a background task
        async def startup():
            # Start trading bot in background
            bot_task = asyncio.create_task(start_trading_bot())
            
            # Keep the startup function running
            try:
                await bot_task
            except Exception as e:
                logging.error(f"Trading bot error: {e}")
        
        # Add startup event to FastAPI
        @app.on_event("startup")
        async def on_startup():
            asyncio.create_task(startup())
        
        # Start the web server
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            log_level=Settings.LOG_LEVEL.lower(),
            access_log=True
        )
        
    except Exception as e:
        print(f"❌ Startup error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()