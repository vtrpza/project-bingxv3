#!/usr/bin/env python3
# scanner/worker.py
"""Scanner worker for continuous asset monitoring and signal generation."""

import asyncio
import logging
import signal
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from scanner.initial_scanner import InitialScanner
from analysis.indicators import IndicatorCalculator
from database.connection import init_database, get_session
from database.repository import AssetRepository, IndicatorRepository, SignalRepository
from api.client import get_client, initialize_client
from config.trading_config import TradingConfig
from utils.logger import get_logger
from utils.rate_limiter import get_rate_limiter
from utils.smart_cache import get_smart_cache
from utils.worker_coordinator import get_coordinator

logger = get_logger(__name__)

class ScannerWorker:
    """Worker for continuous asset scanning and signal generation."""
    
    def __init__(self):
        self.config = TradingConfig()
        self.running = False
        self.scanner = InitialScanner()
        self.indicator_calc = IndicatorCalculator()
        self.asset_repo = AssetRepository()
        self.indicator_repo = IndicatorRepository()
        self.signal_repo = SignalRepository()
        self.rate_limiter = get_rate_limiter()
        self.cache = get_smart_cache()
        self.coordinator = get_coordinator()
        self.worker_id = f"scanner_worker_{id(self)}"
        
    async def initialize(self):
        """Initialize the scanner worker."""
        try:
            logger.info("🔍 Initializing Scanner Worker...")
            
            # Initialize database
            if not init_database():
                raise RuntimeError("Failed to initialize database")
            
            # Register with coordinator
            await self.coordinator.register_worker(self.worker_id, 'scanner')
            
            # Initialize API client
            if not await initialize_client():
                raise RuntimeError("Failed to initialize API client")
                
            logger.info("✅ Scanner Worker initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize scanner worker: {e}")
            return False
    
    async def scan_cycle(self):
        """Execute one complete scan cycle with optimized concurrent processing."""
        try:
            logger.info("🔄 Starting optimized scan cycle...")
            
            with get_session() as session:
                # Get valid assets
                valid_assets = self.asset_repo.get_valid_assets(session)
                if not valid_assets:
                    logger.warning("No valid assets found for scanning")
                    return
                
                logger.info(f"📊 Scanning {len(valid_assets)} valid assets concurrently...")
                
                # Process assets in highly concurrent batches for maximum performance
                max_concurrent = min(30, len(valid_assets))  # Doubled batch size for 2x speed
                signals_generated = 0
                
                for i in range(0, len(valid_assets), max_concurrent):
                    batch = valid_assets[i:i + max_concurrent]
                    
                    # Process batch concurrently
                    batch_tasks = [
                        self._process_single_asset_optimized(asset, session)
                        for asset in batch
                    ]
                    
                    batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                    
                    # Process results
                    for j, result in enumerate(batch_results):
                        asset = batch[j]
                        if isinstance(result, Exception):
                            logger.error(f"Error scanning {asset.symbol}: {result}")
                        elif result:
                            signals_generated += 1
                            logger.info(f"🎯 Signal generated for {asset.symbol}: {result['type']}")
                    
                    # Ultra-fast intelligent delay between batches
                    if i + max_concurrent < len(valid_assets):
                        stats = self.rate_limiter.get_stats()
                        utilization = stats.get('market_data', {}).get('utilization_percent', 0)
                        
                        if utilization < 70:
                            delay = 0.05  # 50ms - Ultra fast
                        elif utilization < 85:
                            delay = 0.15  # 150ms - Fast
                        else:
                            delay = 0.25  # 250ms - Moderate
                            
                        await asyncio.sleep(delay)
                
                session.commit()
                
                # Log performance stats
                cache_stats = self.cache.get_stats()
                rate_stats = self.rate_limiter.get_stats()
                
                logger.info(f"✅ Optimized scan cycle completed - {signals_generated} signals generated")
                logger.info(f"Cache hit rate: {cache_stats['hit_rate_percent']}%")
                logger.info(f"Rate limiter utilization: {rate_stats.get('market_data', {}).get('utilization_percent', 0):.1f}%")
                
        except Exception as e:
            logger.error(f"❌ Error in scan cycle: {e}")
    
    async def _process_single_asset_optimized(self, asset, session):
        """Process a single asset with caching and rate limiting."""
        try:
            client = get_client()
            
            # Fetch ticker data
            ticker = await self._fetch_ticker_with_rate_limit(client, asset.symbol)
            
            if not ticker:
                return None
            
            # Get OHLCV data
            ohlcv_2h = await self._fetch_ohlcv_with_rate_limit(client, asset.symbol, '2h', 100)
            ohlcv_4h = await self._fetch_ohlcv_with_rate_limit(client, asset.symbol, '4h', 100)
            
            if not ohlcv_2h or not ohlcv_4h:
                return None
            
            # Calculate indicators (synchronous operation)
            indicators_2h = self.indicator_calc.calculate_all(ohlcv_2h)
            indicators_4h = self.indicator_calc.calculate_all(ohlcv_4h)
            
            # Store indicators
            await self._store_indicators(session, asset, indicators_2h, '2h')
            await self._store_indicators(session, asset, indicators_4h, '4h')
            
            # Check for trading signals
            signal = await self._check_trading_signals(
                asset, ticker, indicators_2h, indicators_4h
            )
            
            if signal:
                await self._store_signal(session, asset, signal)
                return signal
            
            return None
            
        except Exception as e:
            logger.error(f"Error in optimized processing for {asset.symbol}: {e}")
            return None
    
    async def _fetch_ticker_with_rate_limit(self, client, symbol):
        """Fetch ticker with rate limiting and coordination."""
        await self.coordinator.request_api_permission(self.worker_id, 'market_data')
        await self.rate_limiter.acquire('market_data')
        return await client.fetch_ticker(symbol)
    
    async def _fetch_ohlcv_with_rate_limit(self, client, symbol, timeframe, limit):
        """Fetch OHLCV data with rate limiting and coordination."""
        await self.coordinator.request_api_permission(self.worker_id, 'market_data')
        await self.rate_limiter.acquire('market_data')
        return await client.fetch_ohlcv(symbol, timeframe, limit)
    
    async def _store_indicators(self, session, asset, indicators, timeframe):
        """Store calculated indicators in database."""
        try:
            self.indicator_repo.upsert_indicators(
                session=session,
                asset_id=asset.id,
                timeframe=timeframe,
                timestamp=datetime.utcnow(),
                **indicators
            )
        except Exception as e:
            logger.error(f"Error storing indicators for {asset.symbol} {timeframe}: {e}")
    
    async def _check_trading_signals(self, asset, ticker, indicators_2h, indicators_4h):
        """Check for trading signals based on indicators."""
        try:
            current_price = float(ticker['last'])
            
            # Rule 1: MA Crossover
            signal_2h = self._check_ma_crossover(indicators_2h, current_price, '2h')
            signal_4h = self._check_ma_crossover(indicators_4h, current_price, '4h')
            
            # Rule 2: MA Distance
            distance_signal_2h = self._check_ma_distance(indicators_2h, current_price, '2h')
            distance_signal_4h = self._check_ma_distance(indicators_4h, current_price, '4h')
            
            # Rule 3: Volume Spike (would need volume data)
            # volume_signal = self._check_volume_spike(ticker, historical_volume)
            
            # Return strongest signal
            all_signals = [signal_2h, signal_4h, distance_signal_2h, distance_signal_4h]
            valid_signals = [s for s in all_signals if s]
            
            if valid_signals:
                # Return signal with highest strength
                return max(valid_signals, key=lambda x: x.get('strength', 0))
                
            return None
            
        except Exception as e:
            logger.error(f"Error checking signals for {asset.symbol}: {e}")
            return None
    
    def _check_ma_crossover(self, indicators, current_price, timeframe):
        """Check for moving average crossover signal."""
        try:
            mm1 = indicators.get('mm1')
            center = indicators.get('center')
            rsi = indicators.get('rsi')
            
            if not all([mm1, center, rsi]):
                return None
                
            # RSI between 35 and 73 for Rule 1
            if not (35 <= rsi <= 73):
                return None
                
            # Check crossover
            if mm1 > center:
                return {
                    'type': 'BUY',
                    'rule': 'MA_CROSSOVER',
                    'timeframe': timeframe,
                    'strength': 0.7,
                    'price': current_price,
                    'mm1': mm1,
                    'center': center,
                    'rsi': rsi
                }
            elif mm1 < center:
                return {
                    'type': 'SELL',
                    'rule': 'MA_CROSSOVER',
                    'timeframe': timeframe,
                    'strength': 0.7,
                    'price': current_price,
                    'mm1': mm1,
                    'center': center,
                    'rsi': rsi
                }
                
            return None
            
        except Exception as e:
            logger.error(f"Error in MA crossover check: {e}")
            return None
    
    def _check_ma_distance(self, indicators, current_price, timeframe):
        """Check for moving average distance signal."""
        try:
            mm1 = indicators.get('mm1')
            center = indicators.get('center')
            
            if not all([mm1, center]):
                return None
                
            # Calculate distance percentage
            distance_percent = abs(mm1 - center) / center * 100
            
            # Rule 2: Distance thresholds
            min_distance = 3.0 if timeframe == '4h' else 2.0
            
            if distance_percent >= min_distance:
                signal_type = 'BUY' if mm1 > center else 'SELL'
                return {
                    'type': signal_type,
                    'rule': 'MA_DISTANCE',
                    'timeframe': timeframe,
                    'strength': min(distance_percent / 5.0, 1.0),  # Max strength at 5%
                    'price': current_price,
                    'mm1': mm1,
                    'center': center,
                    'distance_percent': distance_percent
                }
                
            return None
            
        except Exception as e:
            logger.error(f"Error in MA distance check: {e}")
            return None
    
    async def _store_signal(self, session, asset, signal):
        """Store trading signal in database."""
        try:
            self.signal_repo.create(
                session=session,
                asset_id=asset.id,
                timestamp=datetime.utcnow(),
                signal_type=signal['type'],
                strength=signal['strength'],
                rules_triggered=[signal['rule']],
                indicators_snapshot=signal
            )
        except Exception as e:
            logger.error(f"Error storing signal for {asset.symbol}: {e}")
    
    async def run(self):
        """Run the scanner worker continuously."""
        self.running = True
        logger.info("🚀 Scanner Worker started - monitoring assets for signals...")
        
        while self.running:
            try:
                await self.scan_cycle()
                
                # Wait for next cycle
                await asyncio.sleep(self.config.SCAN_INTERVAL)
                
            except KeyboardInterrupt:
                logger.info("👋 Stopping scanner worker...")
                self.running = False
                break
            except Exception as e:
                logger.error(f"❌ Error in scanner worker: {e}")
                await asyncio.sleep(5)  # Wait before retry
    
    async def stop(self):
        """Stop the scanner worker."""
        self.running = False
        logger.info("🛑 Scanner worker stop requested")
        
        # Unregister from coordinator
        try:
            await self.coordinator.unregister_worker(self.worker_id)
            logger.info(f"Unregistered scanner worker from coordinator: {self.worker_id}")
        except Exception as e:
            logger.error(f"Error unregistering from coordinator: {e}")

def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"Received signal {signum}, shutting down...")
    # Set running to False to stop the main loop, cleanup will happen in main()
    worker.running = False

async def main():
    """Main function."""
    global worker
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Create and initialize worker
        worker = ScannerWorker()
        
        if not await worker.initialize():
            logger.error("Failed to initialize scanner worker")
            sys.exit(1)
        
        # Run worker
        await worker.run()
        
    except Exception as e:
        logger.error(f"Fatal error in scanner worker: {e}")
        sys.exit(1)
    finally:
        logger.info("👋 Scanner worker shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())