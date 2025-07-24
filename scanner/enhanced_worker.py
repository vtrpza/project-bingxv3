#!/usr/bin/env python3
# scanner/enhanced_worker.py
"""Enhanced scanner worker with parallel processing capabilities."""

import asyncio
import logging
import signal
import sys
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from scanner.initial_scanner import InitialScanner
from scanner.parallel_scanner import get_parallel_scanner
from analysis.indicators import IndicatorCalculator
from database.connection import init_database, get_session
from database.repository import AssetRepository, IndicatorRepository, SignalRepository
from api.client import get_client, initialize_client
from config.trading_config import TradingConfig
from utils.logger import get_logger
from utils.rate_limiter import get_rate_limiter
from utils.smart_cache import get_smart_cache

logger = get_logger(__name__)


class EnhancedScannerWorker:
    """Enhanced worker with both regular and parallel scanning modes."""
    
    def __init__(self, use_parallel: bool = True):
        self.config = TradingConfig()
        self.running = False
        self.use_parallel = use_parallel
        
        # Initialize components
        self.initial_scanner = InitialScanner()
        self.parallel_scanner = get_parallel_scanner() if use_parallel else None
        self.indicator_calc = IndicatorCalculator()
        self.asset_repo = AssetRepository()
        self.indicator_repo = IndicatorRepository()
        self.signal_repo = SignalRepository()
        self.rate_limiter = get_rate_limiter()
        self.cache = get_smart_cache()
        
        # Performance tracking
        self.scan_metrics = {
            'total_scans': 0,
            'total_scan_time': 0,
            'signals_generated': 0,
            'errors': 0,
            'avg_scan_time': 0,
            'best_scan_time': float('inf'),
            'worst_scan_time': 0
        }
        
    async def initialize(self):
        """Initialize the enhanced scanner worker."""
        try:
            logger.info(f"🚀 Initializing Enhanced Scanner Worker (Parallel Mode: {self.use_parallel})...")
            
            # Initialize database
            if not init_database():
                raise RuntimeError("Failed to initialize database")
            
            # Initialize API client
            if not await initialize_client():
                raise RuntimeError("Failed to initialize API client")
            
            # Perform initial asset validation if needed
            await self._ensure_valid_assets()
            
            logger.info("✅ Enhanced Scanner Worker initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize enhanced scanner worker: {e}")
            return False
    
    async def _ensure_valid_assets(self):
        """Ensure we have valid assets to scan."""
        try:
            with get_session() as session:
                valid_assets = self.asset_repo.get_valid_assets(session)
                
                if not valid_assets:
                    logger.info("No valid assets found, running initial scan...")
                    result = await self.initial_scanner.scan_all_assets(
                        force_refresh=True,
                        max_assets=self.config.MAX_ASSETS_TO_SCAN
                    )
                    logger.info(f"Initial scan completed: {len(result.valid_assets)} valid assets found")
                else:
                    logger.info(f"Found {len(valid_assets)} valid assets ready for scanning")
                    
        except Exception as e:
            logger.error(f"Error ensuring valid assets: {e}")
    
    async def scan_cycle(self):
        """Execute one complete scan cycle with performance tracking."""
        cycle_start = time.time()
        
        try:
            logger.info(f"🔄 Starting {'parallel' if self.use_parallel else 'regular'} scan cycle...")
            
            with get_session() as session:
                # Get valid assets
                valid_assets = self.asset_repo.get_valid_assets(session)
                if not valid_assets:
                    logger.warning("No valid assets found for scanning")
                    return
                
                # Log scan details
                logger.info(f"📊 Scanning {len(valid_assets)} valid assets...")
                
                # Choose scanning method
                if self.use_parallel and self.parallel_scanner:
                    # Use high-performance parallel scanner
                    performance_data = await self.parallel_scanner.scan_assets_parallel(valid_assets)
                    
                    # Update metrics
                    self.scan_metrics['signals_generated'] += performance_data['signals_generated']
                    self.scan_metrics['errors'] += performance_data['errors']
                    
                    # Log performance
                    logger.info(f"✅ Parallel scan completed: "
                              f"{performance_data['assets_scanned']} assets in "
                              f"{performance_data['scan_time_seconds']:.2f}s "
                              f"({performance_data['scan_rate_per_second']:.1f} assets/s)")
                    logger.info(f"📈 Cache hit rate: {performance_data['cache_hit_rate']:.1f}%, "
                              f"API utilization: {performance_data['api_utilization']:.1f}%")
                    
                else:
                    # Use regular optimized scanner
                    signals_generated = await self._regular_scan(valid_assets, session)
                    self.scan_metrics['signals_generated'] += signals_generated
                
                # Update scan metrics
                cycle_time = time.time() - cycle_start
                self.scan_metrics['total_scans'] += 1
                self.scan_metrics['total_scan_time'] += cycle_time
                self.scan_metrics['avg_scan_time'] = (
                    self.scan_metrics['total_scan_time'] / self.scan_metrics['total_scans']
                )
                self.scan_metrics['best_scan_time'] = min(self.scan_metrics['best_scan_time'], cycle_time)
                self.scan_metrics['worst_scan_time'] = max(self.scan_metrics['worst_scan_time'], cycle_time)
                
                # Log summary metrics every 10 scans
                if self.scan_metrics['total_scans'] % 10 == 0:
                    self._log_performance_summary()
                
        except Exception as e:
            logger.error(f"❌ Error in scan cycle: {e}")
            self.scan_metrics['errors'] += 1
    
    async def _regular_scan(self, valid_assets: List, session) -> int:
        """Regular optimized scanning method."""
        # Process assets in concurrent batches
        max_concurrent = min(30, len(valid_assets))
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
                    self.scan_metrics['errors'] += 1
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
        
        logger.info(f"✅ Regular scan cycle completed - {signals_generated} signals generated")
        logger.info(f"Cache hit rate: {cache_stats['hit_rate_percent']}%")
        logger.info(f"Rate limiter utilization: {rate_stats.get('market_data', {}).get('utilization_percent', 0):.1f}%")
        
        return signals_generated
    
    async def _process_single_asset_optimized(self, asset, session):
        """Process a single asset with caching and rate limiting."""
        try:
            client = get_client()
            
            # Use cached data when possible
            ticker = await self.cache.get_or_fetch(
                'ticker', asset.symbol,
                lambda: self._fetch_ticker_with_rate_limit(client, asset.symbol)
            )
            
            # Get OHLCV data with caching
            ohlcv_2h = await self.cache.get_or_fetch(
                'candles', f"{asset.symbol}_2h_100",
                lambda: self._fetch_ohlcv_with_rate_limit(client, asset.symbol, '2h', 100)
            )
            
            ohlcv_4h = await self.cache.get_or_fetch(
                'candles', f"{asset.symbol}_4h_100", 
                lambda: self._fetch_ohlcv_with_rate_limit(client, asset.symbol, '4h', 100)
            )
            
            if not ohlcv_2h or not ohlcv_4h:
                return None
            
            # Calculate indicators with caching
            indicators_2h = await self.cache.get_or_fetch(
                'indicators', f"{asset.symbol}_2h",
                lambda: self.indicator_calc.calculate_all(ohlcv_2h)
            )
            
            indicators_4h = await self.cache.get_or_fetch(
                'indicators', f"{asset.symbol}_4h",
                lambda: self.indicator_calc.calculate_all(ohlcv_4h)
            )
            
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
        """Fetch ticker with rate limiting."""
        await self.rate_limiter.acquire('market_data')
        return await client.fetch_ticker(symbol)
    
    async def _fetch_ohlcv_with_rate_limit(self, client, symbol, timeframe, limit):
        """Fetch OHLCV data with rate limiting."""
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
    
    def _log_performance_summary(self):
        """Log comprehensive performance summary."""
        logger.info(f"""
        📊 PERFORMANCE SUMMARY (Last {self.scan_metrics['total_scans']} scans)
        ├─ Average scan time: {self.scan_metrics['avg_scan_time']:.2f}s
        ├─ Best scan time: {self.scan_metrics['best_scan_time']:.2f}s
        ├─ Worst scan time: {self.scan_metrics['worst_scan_time']:.2f}s
        ├─ Total signals generated: {self.scan_metrics['signals_generated']}
        ├─ Total errors: {self.scan_metrics['errors']}
        └─ Error rate: {(self.scan_metrics['errors'] / self.scan_metrics['total_scans']):.1%}
        """)
    
    async def run(self):
        """Run the enhanced scanner worker continuously."""
        self.running = True
        logger.info(f"🚀 Enhanced Scanner Worker started - monitoring assets for signals...")
        logger.info(f"⚡ Performance mode: {'PARALLEL' if self.use_parallel else 'REGULAR'}")
        logger.info(f"⏱️ Scan interval: {self.config.SCAN_INTERVAL} seconds")
        
        while self.running:
            try:
                await self.scan_cycle()
                
                # Wait for next cycle
                await asyncio.sleep(self.config.SCAN_INTERVAL)
                
            except KeyboardInterrupt:
                logger.info("👋 Stopping enhanced scanner worker...")
                self.running = False
                break
            except Exception as e:
                logger.error(f"❌ Error in enhanced scanner worker: {e}")
                await asyncio.sleep(5)  # Wait before retry
    
    def stop(self):
        """Stop the enhanced scanner worker."""
        self.running = False
        if self.parallel_scanner:
            asyncio.create_task(self.parallel_scanner.cleanup())
        logger.info("🛑 Enhanced scanner worker stop requested")


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"Received signal {signum}, shutting down...")
    worker.stop()


async def main():
    """Main function."""
    global worker
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Check if parallel mode is requested
        use_parallel = os.getenv("USE_PARALLEL_SCANNER", "true").lower() == "true"
        
        # Create and initialize worker
        worker = EnhancedScannerWorker(use_parallel=use_parallel)
        
        if not await worker.initialize():
            logger.error("Failed to initialize enhanced scanner worker")
            sys.exit(1)
        
        # Run worker
        await worker.run()
        
    except Exception as e:
        logger.error(f"Fatal error in enhanced scanner worker: {e}")
        sys.exit(1)
    finally:
        logger.info("👋 Enhanced scanner worker shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())