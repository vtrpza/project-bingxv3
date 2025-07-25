# trading/worker.py
"""Main trading worker that orchestrates all trading components."""

import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from database.connection import DatabaseManager
from database.repository import TradeRepository, OrderRepository, AssetRepository, SignalRepository
from api.client import BingXClient
from config.trading_config import TradingConfig
from utils.logger import get_logger

# Import test mode functions for aggressive testing
try:
    from api.web_api import is_test_mode_active, get_test_mode_config, increment_test_mode_stat
except ImportError:
    # Fallback functions if import fails
    def is_test_mode_active(): return False
    def get_test_mode_config(): return {}
    def increment_test_mode_stat(stat_name, increment=1): pass

from .engine import TradingEngine
from .order_manager import OrderManager
from .risk_manager import RiskManager
from .position_tracker import PositionTracker

logger = get_logger(__name__)


class TradingWorkerError(Exception):
    """Base exception for trading worker errors."""
    pass


class TradingWorker:
    """
    Main trading worker that orchestrates all trading components:
    - Listens for trading signals
    - Coordinates between all trading modules
    - Manages the overall trading lifecycle
    - Provides unified trading API
    """
    
    def __init__(self):
        # Core components
        self.db_manager: Optional[DatabaseManager] = None
        self.client: Optional[BingXClient] = None
        
        # Repositories
        self.trade_repo: Optional[TradeRepository] = None
        self.order_repo: Optional[OrderRepository] = None
        self.asset_repo: Optional[AssetRepository] = None
        self.signal_repo: Optional[SignalRepository] = None
        
        # Trading components
        self.trading_engine: Optional[TradingEngine] = None
        self.order_manager: Optional[OrderManager] = None
        self.risk_manager: Optional[RiskManager] = None
        self.position_tracker: Optional[PositionTracker] = None
        
        # Worker state
        self._is_running = False
        self._signal_listener_task: Optional[asyncio.Task] = None
        self._health_check_task: Optional[asyncio.Task] = None
        
        # Configuration
        self.config = TradingConfig
        
        # Performance metrics
        self._stats = {
            'signals_processed': 0,
            'trades_executed': 0,
            'orders_created': 0,
            'errors_encountered': 0,
            'uptime_start': None
        }
        
        logger.info("TradingWorker initialized")
    
    async def initialize(self):
        """Initialize all trading components."""
        try:
            logger.info("🚀 Initializing TradingWorker...")
            
            # Initialize database
            from database.connection import init_database
            if not init_database():
                raise TradingWorkerError("Failed to initialize database connection")
            self.db_manager = None  # Use global instance
            
            # Initialize API client
            self.client = BingXClient()
            await self.client.initialize()
            
            # Initialize repositories
            self.trade_repo = TradeRepository()
            self.order_repo = OrderRepository()
            self.asset_repo = AssetRepository()
            self.signal_repo = SignalRepository()
            
            # Initialize trading components
            self.order_manager = OrderManager(self.client, self.order_repo, self.trade_repo)
            self.risk_manager = RiskManager(self.client, self.trade_repo, self.order_manager)
            self.position_tracker = PositionTracker(self.client, self.trade_repo)
            self.trading_engine = TradingEngine(self.client, self.trade_repo, self.asset_repo)
            
            # Start all components
            await self.order_manager.start()
            await self.risk_manager.start()
            await self.position_tracker.start()
            await self.trading_engine.start()
            
            # Validate configuration
            config_errors = self.config.validate()
            if config_errors:
                raise TradingWorkerError(f"Configuration errors: {config_errors}")
            
            logger.info("✅ TradingWorker initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize TradingWorker: {e}")
            await self.cleanup()
            raise TradingWorkerError(f"Initialization failed: {e}")
    
    async def start(self):
        """Start the trading worker."""
        try:
            if self._is_running:
                logger.warning("TradingWorker is already running")
                return
            
            logger.info("🚀 Starting TradingWorker...")
            
            # Set up signal handlers for graceful shutdown
            self._setup_signal_handlers()
            
            # Mark as running
            self._is_running = True
            self._stats['uptime_start'] = datetime.now(timezone.utc)
            
            # Start signal listener
            self._signal_listener_task = asyncio.create_task(self._listen_for_signals())
            
            # Start health check task
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            
            logger.info("✅ TradingWorker started successfully")
            
            # Log startup information
            await self._log_startup_info()
            
        except Exception as e:
            logger.error(f"Failed to start TradingWorker: {e}")
            await self.stop()
            raise TradingWorkerError(f"Startup failed: {e}")
    
    async def stop(self):
        """Stop the trading worker gracefully."""
        try:
            if not self._is_running:
                logger.info("TradingWorker is already stopped")
                return
            
            logger.info("🛑 Stopping TradingWorker...")
            
            # Stop accepting new signals
            self._is_running = False
            
            # Cancel background tasks
            if self._signal_listener_task:
                self._signal_listener_task.cancel()
                try:
                    await self._signal_listener_task
                except asyncio.CancelledError:
                    pass
            
            if self._health_check_task:
                self._health_check_task.cancel()
                try:
                    await self._health_check_task
                except asyncio.CancelledError:
                    pass
            
            # Stop all trading components
            if self.trading_engine:
                await self.trading_engine.stop()
            
            if self.position_tracker:
                await self.position_tracker.stop()
            
            if self.risk_manager:
                await self.risk_manager.stop()
            
            if self.order_manager:
                await self.order_manager.stop()
            
            # Cleanup resources
            await self.cleanup()
            
            logger.info("✅ TradingWorker stopped successfully")
            
        except Exception as e:
            logger.error(f"Error stopping TradingWorker: {e}")
    
    async def cleanup(self):
        """Cleanup resources."""
        try:
            if self.client:
                await self.client.close()
            
            if self.db_manager:
                self.db_manager.close()
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    async def process_signal(self, signal_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process a trading signal manually.
        
        Args:
            signal_data: Signal data dictionary
            
        Returns:
            Trade result or None if not executed
        """
        try:
            if not self._is_running:
                logger.warning("TradingWorker not running, cannot process signal")
                return None
            
            logger.info(f"📊 Processing signal: {signal_data.get('symbol')} {signal_data.get('signal_type')}")
            
            # Update stats
            self._stats['signals_processed'] += 1
            
            # Check risk limits first
            risk_check, risk_reasons = await self.risk_manager.check_risk_limits(signal_data)
            if not risk_check:
                logger.warning(f"❌ Signal rejected by risk manager: {risk_reasons}")
                return None
            
            # Process through trading engine
            trade_result = await self.trading_engine.process_signal(signal_data)
            
            if trade_result:
                # Update stats
                self._stats['trades_executed'] += 1
                
                # Add position to tracker
                trade = await self.trade_repo.get_by_id(trade_result['trade_id'])
                if trade:
                    await self.position_tracker.add_position(trade)
                
                # Initialize risk management
                await self.risk_manager.initialize_trailing_stop(
                    trade_result['trade_id'],
                    trade_result['entry_price'],
                    trade_result['side']
                )
                
                logger.info(f"✅ Trade executed successfully: {trade_result}")
                
                return trade_result
            
            return None
            
        except Exception as e:
            logger.error(f"Error processing signal: {e}")
            self._stats['errors_encountered'] += 1
            return None
    
    async def _listen_for_signals(self):
        """Listen for trading signals from the signal queue."""
        logger.info("🎧 Starting signal listener...")
        
        while self._is_running:
            try:
                # Get pending signals from database
                from database.connection import get_session
                with get_session() as session:
                    pending_signals = self.signal_repo.get_pending_signals(session, limit=10)
                
                for signal in pending_signals:
                    if not self._is_running:
                        break
                    
                    try:
                        # Convert signal to dict format
                        signal_data = {
                            'symbol': signal.asset.symbol,
                            'signal_type': signal.signal_type,
                            'strength': signal.strength,
                            'rules_triggered': signal.rules_triggered,
                            'indicators_snapshot': signal.indicators_snapshot,
                            'timestamp': signal.timestamp
                        }
                        
                        # Process the signal
                        result = await self.process_signal(signal_data)
                        
                        # Update signal status
                        with get_session() as session:
                            if result:
                                self.signal_repo.mark_signal_processed(session, signal.id, result['trade_id'])
                            else:
                                self.signal_repo.mark_signal_rejected(session, signal.id, "Trading conditions not met")
                        
                    except Exception as e:
                        logger.error(f"Error processing signal {signal.id}: {e}")
                        with get_session() as session:
                            self.signal_repo.mark_signal_rejected(session, signal.id, f"Processing error: {str(e)}")
                
                # Wait before checking for more signals
                await asyncio.sleep(5)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in signal listener: {e}")
                self._stats['errors_encountered'] += 1
                await asyncio.sleep(10)
        
        logger.info("🎧 Signal listener stopped")
    
    async def _health_check_loop(self):
        """Periodic health check of all components."""
        logger.info("🏥 Starting health check loop...")
        
        while self._is_running:
            try:
                await self._perform_health_check()
                
                # Log status every hour
                current_time = datetime.now(timezone.utc)
                if current_time.minute == 0:  # Top of the hour
                    await self._log_periodic_status()
                
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check: {e}")
                await asyncio.sleep(60)
        
        logger.info("🏥 Health check loop stopped")
    
    async def _perform_health_check(self):
        """Perform health check on all components."""
        try:
            health_status = {
                'database': await self._check_database_health(),
                'api_client': await self._check_api_health(),
                'trading_engine': self.trading_engine._is_running if self.trading_engine else False,
                'order_manager': self.order_manager._is_running if self.order_manager else False,
                'risk_manager': self.risk_manager._is_running if self.risk_manager else False,
                'position_tracker': self.position_tracker._is_running if self.position_tracker else False
            }
            
            # Check for any unhealthy components
            unhealthy = [name for name, status in health_status.items() if not status]
            
            if unhealthy:
                logger.warning(f"⚠️ Unhealthy components detected: {unhealthy}")
                # Could implement auto-recovery here
            
        except Exception as e:
            logger.error(f"Error in health check: {e}")
    
    async def _check_database_health(self) -> bool:
        """Check database connectivity."""
        try:
            if not self.db_manager:
                return False
            
            # Try a simple query
            result = await self.asset_repo.get_asset_count()
            return result is not None
            
        except Exception:
            return False
    
    async def _check_api_health(self) -> bool:
        """Check API client connectivity."""
        try:
            if not self.client:
                return False
            
            # Try to fetch a ticker
            await self.client.fetch_ticker('BTC/USDT')
            return True
            
        except Exception:
            return False
    
    async def _log_startup_info(self):
        """Log startup information."""
        try:
            config_info = self.config.get_info()
            
            logger.info("📋 Trading Configuration:")
            logger.info(f"  • Max concurrent trades: {config_info['max_concurrent_trades']}")
            logger.info(f"  • Position size: {config_info['max_position_percent']}% of balance")
            logger.info(f"  • Initial stop loss: {config_info['initial_stop_loss']*100:.1f}%")
            logger.info(f"  • Trading enabled: {config_info['trading_enabled']}")
            logger.info(f"  • Paper trading: {config_info['paper_trading']}")
            logger.info(f"  • Emergency stop: {config_info['emergency_stop']}")
            
            # Log current positions
            positions = await self.position_tracker.get_all_positions()
            logger.info(f"📊 Current positions: {len(positions)}")
            
            # Log account balance
            trading_stats = await self.trading_engine.get_trading_stats()
            logger.info(f"💰 USDT Balance: {trading_stats.get('usdt_balance', 0):.2f}")
            
        except Exception as e:
            logger.error(f"Error logging startup info: {e}")
    
    async def _log_periodic_status(self):
        """Log periodic status information."""
        try:
            # Calculate uptime
            uptime = datetime.now(timezone.utc) - self._stats['uptime_start']
            uptime_hours = uptime.total_seconds() / 3600
            
            # Get current metrics
            portfolio_metrics = await self.position_tracker.get_portfolio_metrics()
            risk_metrics = await self.risk_manager.get_risk_metrics()
            trading_stats = await self.trading_engine.get_trading_stats()
            
            logger.info("=" * 60)
            logger.info("📊 TRADING WORKER STATUS REPORT")
            logger.info("=" * 60)
            logger.info(f"⏱️  Uptime: {uptime_hours:.1f} hours")
            logger.info(f"📈 Signals processed: {self._stats['signals_processed']}")
            logger.info(f"💼 Trades executed: {self._stats['trades_executed']}")
            logger.info(f"📋 Orders created: {self._stats['orders_created']}")
            logger.info(f"❌ Errors encountered: {self._stats['errors_encountered']}")
            
            if portfolio_metrics:
                logger.info(f"💰 Portfolio P&L: {portfolio_metrics['total_unrealized_pnl']:.2f} USDT "
                           f"({portfolio_metrics['total_unrealized_pnl_percent']:.2%})")
                logger.info(f"📊 Active positions: {portfolio_metrics['total_positions']}")
                logger.info(f"📅 Daily P&L: {portfolio_metrics['daily_pnl']:.2f} USDT")
            
            if risk_metrics:
                logger.info(f"⚠️  Risk score: {risk_metrics['risk_score']:.2f}")
                logger.info(f"📊 Win rate: {risk_metrics['win_rate']:.1%}")
            
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"Error logging periodic status: {e}")
    
    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown."""
        def signal_handler(sig, frame):
            logger.info(f"Received signal {sig}, initiating graceful shutdown...")
            asyncio.create_task(self.stop())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    # Public API methods
    
    async def get_status(self) -> Dict[str, Any]:
        """Get comprehensive worker status."""
        try:
            uptime = None
            if self._stats['uptime_start']:
                uptime = (datetime.now(timezone.utc) - self._stats['uptime_start']).total_seconds()
            
            return {
                'is_running': self._is_running,
                'uptime_seconds': uptime,
                'stats': self._stats.copy(),
                'portfolio_metrics': await self.position_tracker.get_portfolio_metrics() if self.position_tracker else None,
                'risk_metrics': await self.risk_manager.get_risk_metrics() if self.risk_manager else None,
                'trading_stats': await self.trading_engine.get_trading_stats() if self.trading_engine else None,
            }
            
        except Exception as e:
            logger.error(f"Error getting worker status: {e}")
            return {'error': str(e)}
    
    async def emergency_stop(self) -> bool:
        """Trigger emergency stop of all trading."""
        try:
            logger.warning("🚨 EMERGENCY STOP TRIGGERED")
            
            success = True
            
            # Stop trading engine
            if self.trading_engine:
                result = await self.trading_engine.emergency_stop_all()
                success = success and result
            
            # Stop accepting new signals
            self._is_running = False
            
            logger.warning(f"🚨 Emergency stop {'completed' if success else 'failed'}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error during emergency stop: {e}")
            return False
    
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get all current positions."""
        if not self.position_tracker:
            return []
        
        return await self.position_tracker.get_all_positions()
    
    async def get_orders(self) -> List[Dict[str, Any]]:
        """Get all active orders."""
        if not self.order_manager:
            return []
        
        return await self.order_manager.get_active_orders()


# Main entry point for running the trading worker
async def main():
    """Main entry point for the trading worker."""
    worker = TradingWorker()
    
    try:
        await worker.initialize()
        await worker.start()
        
        # Keep running until interrupted
        while worker._is_running:
            await asyncio.sleep(1)
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Fatal error in trading worker: {e}")
    finally:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(main())