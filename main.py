#!/usr/bin/env python3
# main.py
"""BingX Trading Bot - Main Entry Point"""

import asyncio
import signal
import sys
import os
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from config.trading_config import TradingConfig
from database.connection import DatabaseManager, get_session, init_database, create_tables
from database.repository import AssetRepository, TradeRepository, OrderRepository
from api.client import BingXClient
from scanner.initial_scanner import InitialScanner
from trading.engine import TradingEngine
from trading.order_manager import OrderManager
from trading.risk_manager import RiskManager
from utils.logger import get_logger, setup_module_logger

# Setup logging
logger = setup_module_logger(__name__, Settings.LOG_LEVEL)


class TradingBot:
    """Main trading bot orchestrator."""
    
    def __init__(self):
        self.is_running = False
        self.components = {}
        
        # Database
        self.db_manager: Optional[DatabaseManager] = None
        
        # Repositories
        self.asset_repo: Optional[AssetRepository] = None
        self.trade_repo: Optional[TradeRepository] = None
        self.order_repo: Optional[OrderRepository] = None
        
        # API Client
        self.client: Optional[BingXClient] = None
        
        # Core Components
        self.scanner: Optional[InitialScanner] = None
        self.order_manager: Optional[OrderManager] = None
        self.risk_manager: Optional[RiskManager] = None
        self.trading_engine: Optional[TradingEngine] = None
        
        # Tasks
        self.scanner_task: Optional[asyncio.Task] = None
        self.trading_task: Optional[asyncio.Task] = None
        
        logger.info("🤖 BingX Trading Bot initialized")
    
    async def initialize(self):
        """Initialize all bot components."""
        try:
            logger.info("🚀 Initializing BingX Trading Bot...")
            
            # Validate configuration
            self._validate_configuration()
            
            # Initialize database
            await self._initialize_database()
            
            # Initialize repositories
            self._initialize_repositories()
            
            # Initialize API client
            await self._initialize_api_client()
            
            # Initialize components
            await self._initialize_components()
            
            logger.info("✅ Bot initialization completed successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize bot: {e}")
            raise
    
    def _validate_configuration(self):
        """Validate bot configuration."""
        logger.info("📋 Validating configuration...")
        
        # Check required environment variables
        required_vars = ['BINGX_API_KEY', 'BINGX_SECRET_KEY', 'DATABASE_URL']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {missing_vars}")
        
        # Validate trading configuration
        config_errors = TradingConfig.validate()
        if config_errors:
            raise ValueError(f"Trading configuration errors: {config_errors}")
        
        logger.info("✅ Configuration validation passed")
    
    async def _initialize_database(self):
        """Initialize database connection and create tables."""
        logger.info("🗄️ Initializing database...")
        
        try:
            # Initialize global database manager
            if not init_database():
                raise RuntimeError("Failed to initialize database")
            
            # Create tables if they don't exist
            if not create_tables():
                raise RuntimeError("Failed to create database tables")
            
            # Test database connection
            with get_session() as session:
                from sqlalchemy import text
                session.execute(text("SELECT 1"))
            
            logger.info("✅ Database initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            raise
    
    def _initialize_repositories(self):
        """Initialize data repositories."""
        logger.info("📚 Initializing repositories...")
        
        self.asset_repo = AssetRepository()
        self.trade_repo = TradeRepository()
        self.order_repo = OrderRepository()
        
        logger.info("✅ Repositories initialized")
    
    async def _initialize_api_client(self):
        """Initialize BingX API client."""
        logger.info("🌐 Initializing API client...")
        
        try:
            self.client = BingXClient()
            await self.client.initialize()
            
            # Test API connection
            balance = await self.client.fetch_balance()
            logger.info(f"✅ API client initialized - Balance: {balance.get('USDT', {}).get('free', 0)} USDT")
            
        except Exception as e:
            logger.error(f"❌ API client initialization failed: {e}")
            raise
    
    async def _initialize_components(self):
        """Initialize trading bot components."""
        logger.info("⚙️ Initializing bot components...")
        
        try:
            # Initialize scanner
            self.scanner = InitialScanner(
                client=self.client,
                asset_repo=self.asset_repo
            )
            
            # Initialize order manager
            self.order_manager = OrderManager(
                client=self.client,
                order_repo=self.order_repo,
                trade_repo=self.trade_repo
            )
            
            # Initialize risk manager
            self.risk_manager = RiskManager(
                client=self.client,
                trade_repo=self.trade_repo,
                order_manager=self.order_manager
            )
            
            # Initialize trading engine
            self.trading_engine = TradingEngine(
                client=self.client,
                trade_repo=self.trade_repo,
                asset_repo=self.asset_repo
            )
            
            # Store components for cleanup
            self.components = {
                'scanner': self.scanner,
                'order_manager': self.order_manager,
                'risk_manager': self.risk_manager,
                'trading_engine': self.trading_engine
            }
            
            logger.info("✅ Bot components initialized")
            
        except Exception as e:
            logger.error(f"❌ Component initialization failed: {e}")
            raise
    
    async def start(self):
        """Start the trading bot."""
        if self.is_running:
            logger.warning("Bot is already running")
            return
        
        try:
            logger.info("🚀 Starting BingX Trading Bot...")
            self.is_running = True
            
            # Start all components
            await self.order_manager.start()
            await self.risk_manager.start()
            await self.trading_engine.start()
            
            # Start background tasks
            await self._start_background_tasks()
            
            logger.info("✅ BingX Trading Bot started successfully")
            logger.info(f"📊 Configuration: {TradingConfig.get_info()}")
            
        except Exception as e:
            logger.error(f"❌ Failed to start bot: {e}")
            self.is_running = False
            raise
    
    async def _start_background_tasks(self):
        """Start background monitoring tasks."""
        logger.info("📡 Starting background tasks...")
        
        # Start scanner task
        self.scanner_task = asyncio.create_task(self._run_scanner())
        
        # Start trading monitoring task
        self.trading_task = asyncio.create_task(self._run_trading_monitor())
        
        logger.info("✅ Background tasks started")
    
    async def _run_scanner(self):
        """Run the asset scanner continuously."""
        logger.info("🔍 Starting asset scanner...")
        
        try:
            # Initial scan to validate assets
            await self.scanner.perform_initial_scan()
            
            while self.is_running:
                try:
                    # Continuous scanning for trading signals
                    valid_assets = await self.scanner.get_valid_assets_for_scanning()
                    
                    if valid_assets:
                        logger.debug(f"Scanning {len(valid_assets)} valid assets for signals")
                        
                        # Here would be the continuous scanning logic
                        # For now, just wait
                        await asyncio.sleep(TradingConfig.SCAN_INTERVAL_SECONDS)
                    else:
                        logger.warning("No valid assets found for scanning")
                        await asyncio.sleep(60)  # Wait longer if no assets
                
                except Exception as e:
                    logger.error(f"Error in scanner loop: {e}")
                    await asyncio.sleep(30)
        
        except asyncio.CancelledError:
            logger.info("Scanner task cancelled")
        except Exception as e:
            logger.error(f"Scanner task error: {e}")
    
    async def _run_trading_monitor(self):
        """Run trading monitoring and signal processing."""
        logger.info("📈 Starting trading monitor...")
        
        try:
            while self.is_running:
                try:
                    # Get trading statistics
                    stats = await self.trading_engine.get_trading_stats()
                    risk_metrics = await self.risk_manager.get_risk_metrics()
                    
                    # Log status every 5 minutes
                    if datetime.now().minute % 5 == 0:
                        logger.info(f"📊 Trading Status - Active: {stats.get('open_trades', 0)}, "
                                  f"Balance: {stats.get('usdt_balance', 0):.2f} USDT, "
                                  f"Risk Score: {risk_metrics.get('risk_score', 0):.2f}")
                    
                    await asyncio.sleep(30)  # Check every 30 seconds
                
                except Exception as e:
                    logger.error(f"Error in trading monitor: {e}")
                    await asyncio.sleep(30)
        
        except asyncio.CancelledError:
            logger.info("Trading monitor task cancelled")
        except Exception as e:
            logger.error(f"Trading monitor task error: {e}")
    
    async def stop(self):
        """Stop the trading bot gracefully."""
        if not self.is_running:
            return
        
        logger.info("🛑 Stopping BingX Trading Bot...")
        self.is_running = False
        
        try:
            # Cancel background tasks
            if self.scanner_task:
                self.scanner_task.cancel()
                try:
                    await self.scanner_task
                except asyncio.CancelledError:
                    pass
            
            if self.trading_task:
                self.trading_task.cancel()
                try:
                    await self.trading_task
                except asyncio.CancelledError:
                    pass
            
            # Stop all components
            for name, component in self.components.items():
                try:
                    if hasattr(component, 'stop'):
                        await component.stop()
                        logger.info(f"✅ {name} stopped")
                except Exception as e:
                    logger.error(f"Error stopping {name}: {e}")
            
            # Close database connections
            if self.db_manager:
                await self.db_manager.close()
            
            logger.info("✅ BingX Trading Bot stopped successfully")
            
        except Exception as e:
            logger.error(f"Error during bot shutdown: {e}")
    
    async def get_status(self) -> dict:
        """Get current bot status."""
        if not self.is_running:
            return {'status': 'stopped'}
        
        try:
            status = {
                'status': 'running',
                'timestamp': datetime.utcnow().isoformat(),
                'components': {}
            }
            
            # Get component statuses
            if self.trading_engine:
                status['components']['trading'] = await self.trading_engine.get_trading_stats()
            
            if self.risk_manager:
                status['components']['risk'] = await self.risk_manager.get_risk_metrics()
            
            if self.order_manager:
                status['components']['orders'] = await self.order_manager.get_order_stats()
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting bot status: {e}")
            return {'status': 'error', 'error': str(e)}


async def signal_handler(bot: TradingBot):
    """Handle shutdown signals."""
    logger.info("📡 Received shutdown signal")
    await bot.stop()


async def main():
    """Main entry point."""
    bot = None
    
    try:
        # Create and initialize bot
        bot = TradingBot()
        await bot.initialize()
        
        # Setup signal handlers
        loop = asyncio.get_event_loop()
        for sig in [signal.SIGTERM, signal.SIGINT]:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(signal_handler(bot)))
        
        # Start bot
        await bot.start()
        
        # Keep running
        logger.info("🤖 Bot is running. Press Ctrl+C to stop.")
        
        try:
            while bot.is_running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("📡 Received keyboard interrupt")
        
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)
    
    finally:
        if bot:
            await bot.stop()


if __name__ == "__main__":
    try:
        # Check Python version
        if sys.version_info < (3, 8):
            print("❌ Python 3.8+ is required")
            sys.exit(1)
        
        # Create logs directory
        os.makedirs(Settings.LOGS_DIR, exist_ok=True)
        
        # Run the bot
        asyncio.run(main())
        
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Startup error: {e}")
        sys.exit(1)