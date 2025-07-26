# trading/signal_processor.py
"""Signal processor that integrates analysis modules with trading flow."""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
from decimal import Decimal

from analysis.signals import SignalGenerator
from api.market_data import get_market_data_api
from trading.symbol_selector import get_symbol_selector
from trading.worker import TradingWorker
from trading.trading_cache import TradingCache
from database.models import Signal as SignalModel, Asset
from database.repository import SignalRepository, AssetRepository
from database.connection import get_session
from utils.logger import get_logger, trading_logger
from utils.validators import Validator

logger = get_logger(__name__)


class SignalProcessorError(Exception):
    """Exception for signal processor errors."""
    pass


class SignalProcessor:
    """
    Integrates analysis modules with trading flow:
    - Gets symbols from symbol selector
    - Generates signals using analysis modules
    - Sends signals to trading engine
    - Updates web interface
    """
    
    def __init__(self):
        self.symbol_selector = get_symbol_selector()
        self.signal_generator = SignalGenerator()
        self.market_api = get_market_data_api()
        self.trading_cache = TradingCache()
        self.signal_repo = SignalRepository()
        self.asset_repo = AssetRepository()
        self.trading_worker: Optional[TradingWorker] = None
        
        # Processing state
        self._is_running = False
        self._processing_task: Optional[asyncio.Task] = None
        self._last_process_time = {}  # symbol -> last process timestamp
        self._process_interval = 60  # seconds between processing same symbol
        
        logger.info("SignalProcessor initialized")
    
    def set_trading_worker(self, worker: TradingWorker):
        """Set the trading worker instance."""
        self.trading_worker = worker
    
    async def start(self):
        """Start the signal processor."""
        if self._is_running:
            logger.warning("SignalProcessor already running")
            return
        
        self._is_running = True
        self._processing_task = asyncio.create_task(self._continuous_processing())
        logger.info("🚀 SignalProcessor started")
    
    async def stop(self):
        """Stop the signal processor."""
        self._is_running = False
        
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
        
        logger.info("🛑 SignalProcessor stopped")
    
    async def _continuous_processing(self):
        """Continuously process signals for selected symbols."""
        logger.info("Starting continuous signal processing...")
        
        while self._is_running:
            try:
                # Get trading symbols from selector
                selected_symbols = await self.symbol_selector.select_trading_symbols()
                
                if not selected_symbols:
                    logger.warning("No symbols selected for trading")
                    await asyncio.sleep(30)  # Wait before retry
                    continue
                
                logger.info(f"Processing signals for {len(selected_symbols)} symbols")
                
                # Process each symbol
                tasks = []
                for trading_symbol in selected_symbols[:5]:  # Limit to top 5 for efficiency
                    # Check if enough time has passed since last processing
                    symbol = trading_symbol.symbol
                    last_time = self._last_process_time.get(symbol, 0)
                    current_time = datetime.now(timezone.utc).timestamp()
                    
                    if current_time - last_time >= self._process_interval:
                        task = asyncio.create_task(self._process_symbol(trading_symbol))
                        tasks.append(task)
                        self._last_process_time[symbol] = current_time
                
                # Wait for all symbol processing to complete
                if tasks:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Log results
                    successful = sum(1 for r in results if r and not isinstance(r, Exception))
                    logger.info(f"Signal processing complete: {successful}/{len(tasks)} successful")
                
                # Wait before next cycle
                await asyncio.sleep(10)  # Process every 10 seconds
                
            except Exception as e:
                logger.error(f"Error in continuous processing: {e}")
                await asyncio.sleep(30)
    
    async def _process_symbol(self, trading_symbol) -> Optional[Dict[str, Any]]:
        """Process signals for a single symbol."""
        try:
            symbol = trading_symbol.symbol
            logger.debug(f"Processing signals for {symbol}")
            
            # Fetch candle data for different timeframes
            candles_spot = await self._fetch_candles(symbol, '1m', 100)
            candles_2h = await self._fetch_candles(symbol, '2h', 100)
            candles_4h = await self._fetch_candles(symbol, '4h', 100)
            
            if not all([candles_spot, candles_2h, candles_4h]):
                logger.warning(f"Insufficient candle data for {symbol}")
                return None
            
            # Generate signal using analysis module
            signal_result = self.signal_generator.generate_trading_signal(
                symbol, candles_spot, candles_2h, candles_4h
            )
            
            if not signal_result or signal_result.get('signal') == 'NEUTRAL':
                logger.debug(f"No actionable signal for {symbol}")
                return None
            
            # Prepare signal data for trading
            signal_data = {
                'symbol': symbol,
                'signal_type': signal_result['signal'],
                'strength': signal_result.get('signal_strength', 0.5),
                'rules_triggered': signal_result.get('rules_triggered', []),
                'indicators_snapshot': signal_result.get('indicators', {}),
                'volume_24h': trading_symbol.volume_24h,
                'liquidity_score': trading_symbol.liquidity_score,
                'timestamp': datetime.now(timezone.utc)
            }
            
            # Store signal in database
            signal_id = await self._store_signal(signal_data)
            if signal_id:
                signal_data['signal_id'] = signal_id
            
            # Update trading cache for web interface
            await self._update_cache(symbol, signal_data)
            
            # Send to trading worker if available
            if self.trading_worker and self.trading_worker._is_running:
                logger.info(f"📤 Sending signal to trading engine: {symbol} {signal_data['signal_type']}")
                trade_result = await self.trading_worker.process_signal(signal_data)
                
                if trade_result:
                    logger.info(f"✅ Trade executed from signal: {trade_result}")
                    trading_logger.info(f"SIGNAL_TRADE_EXECUTED: {symbol} {signal_data['signal_type']} -> {trade_result}")
                    return trade_result
                else:
                    logger.debug(f"Signal not executed for {symbol}")
            
            return signal_data
            
        except Exception as e:
            logger.error(f"Error processing symbol {trading_symbol.symbol}: {e}")
            return None
    
    async def _store_signal(self, signal_data: Dict[str, Any]) -> Optional[int]:
        """Store signal in database."""
        try:
            with get_session() as session:
                # Get asset
                asset = self.asset_repo.get_by_symbol(session, signal_data['symbol'])
                if not asset:
                    logger.error(f"Asset not found: {signal_data['symbol']}")
                    return None
                
                # Create signal record
                signal = SignalModel(
                    asset_id=asset.id,
                    signal_type=signal_data['signal_type'],
                    strength=float(signal_data['strength']),
                    rules_triggered=signal_data['rules_triggered'],
                    indicators_snapshot=signal_data['indicators_snapshot'],
                    status='pending',
                    created_at=signal_data['timestamp']
                )
                
                created = self.signal_repo.create(session, signal)
                return created.id if created else None
                
        except Exception as e:
            logger.error(f"Error storing signal: {e}")
            return None
    
    async def _update_cache(self, symbol: str, signal_data: Dict[str, Any]):
        """Update trading cache for web interface."""
        try:
            # Update signal in cache
            self.trading_cache.update_signal(symbol, {
                'signal': signal_data['signal_type'],
                'strength': signal_data['strength'],
                'rules': signal_data['rules_triggered'],
                'timestamp': signal_data['timestamp'].isoformat()
            })
            
            # Update indicators if available
            if 'indicators_snapshot' in signal_data:
                indicators = signal_data['indicators_snapshot']
                for timeframe in ['spot', '2h', '4h']:
                    if timeframe in indicators:
                        self.trading_cache.update_indicators(
                            symbol, 
                            timeframe, 
                            indicators[timeframe]
                        )
            
            logger.debug(f"Cache updated for {symbol}")
            
        except Exception as e:
            logger.error(f"Error updating cache: {e}")
    
    async def _fetch_candles(self, symbol: str, timeframe: str, limit: int) -> Optional[List[Dict[str, Any]]]:
        """Fetch candle data for a symbol and timeframe."""
        try:
            candles = await self.market_api.get_candles(symbol, timeframe, limit=limit)
            return candles
        except Exception as e:
            logger.error(f"Error fetching {timeframe} candles for {symbol}: {e}")
            return None
    
    async def process_manual_signal(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Process signal for a specific symbol on demand."""
        try:
            # Validate symbol
            if not Validator.is_valid_symbol(symbol):
                raise SignalProcessorError(f"Invalid symbol: {symbol}")
            
            # Fetch candle data
            candles_spot = await self._fetch_candles(symbol, '1m', 100)
            candles_2h = await self._fetch_candles(symbol, '2h', 100)
            candles_4h = await self._fetch_candles(symbol, '4h', 100)
            
            if not all([candles_spot, candles_2h, candles_4h]):
                raise SignalProcessorError("Insufficient candle data")
            
            # Generate signal
            signal_result = self.signal_generator.generate_trading_signal(
                symbol, candles_spot, candles_2h, candles_4h
            )
            
            if not signal_result:
                return None
            
            # Create trading symbol data
            from trading.symbol_selector import TradingSymbol
            trading_symbol = TradingSymbol(
                symbol=symbol,
                volume_24h=100000,  # Default values for manual processing
                spread_percent=0.1,
                volatility_24h=2.0,
                liquidity_score=0.8,
                selection_score=0.7,
                selection_reasons=['Manual request']
            )
            
            # Process the symbol
            return await self._process_symbol(trading_symbol)
            
        except Exception as e:
            logger.error(f"Error in manual signal processing: {e}")
            raise SignalProcessorError(f"Failed to process signal: {e}")


# Global instance
_signal_processor: Optional[SignalProcessor] = None


def get_signal_processor() -> SignalProcessor:
    """Get or create global signal processor instance."""
    global _signal_processor
    if _signal_processor is None:
        _signal_processor = SignalProcessor()
    return _signal_processor