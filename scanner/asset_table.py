# scanner/asset_table.py
"""Comprehensive asset validation table with all relevant trading metrics."""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from enum import Enum

from api.market_data import get_market_data_api, MarketDataError
from analysis.indicators import get_technical_indicators, IndicatorError
from scanner.validator import get_asset_validator
from config.trading_config import TradingConfig
from utils.logger import get_logger
from utils.formatters import PriceFormatter
from utils.rate_limiter import get_rate_limiter
from utils.smart_cache import get_smart_cache, cached
from database.repository import AssetRepository

logger = get_logger(__name__)


class ValidationStatus(Enum):
    """Asset validation status enumeration."""
    VALID = "VALID"
    INVALID = "INVALID"
    PENDING = "PENDING"
    ERROR = "ERROR"


@dataclass
class AssetMetrics:
    """Complete asset metrics for validation table."""
    
    # Basic Info
    symbol: str
    base_currency: str
    quote_currency: str
    
    # Price Data
    current_price: Optional[Decimal] = None
    price_change_24h: Optional[Decimal] = None
    price_change_percent_24h: Optional[Decimal] = None
    
    # Volume Data
    volume_24h_base: Optional[Decimal] = None
    volume_24h_quote: Optional[Decimal] = None
    volume_change_percent: Optional[Decimal] = None
    trades_count_24h: Optional[int] = None
    
    # Liquidity Data
    bid_price: Optional[Decimal] = None
    ask_price: Optional[Decimal] = None
    spread_percent: Optional[Decimal] = None
    
    # Technical Indicators - Spot
    mm1_spot: Optional[Decimal] = None
    center_spot: Optional[Decimal] = None
    rsi_spot: Optional[Decimal] = None
    
    # Technical Indicators - 2H
    mm1_2h: Optional[Decimal] = None
    center_2h: Optional[Decimal] = None
    rsi_2h: Optional[Decimal] = None
    
    # Technical Indicators - 4H
    mm1_4h: Optional[Decimal] = None
    center_4h: Optional[Decimal] = None
    rsi_4h: Optional[Decimal] = None
    
    # Trading Analysis
    ma_distance_2h: Optional[Decimal] = None
    ma_distance_4h: Optional[Decimal] = None
    ma_direction_2h: Optional[str] = None
    ma_direction_4h: Optional[str] = None
    rsi_condition_2h: Optional[str] = None
    rsi_condition_4h: Optional[str] = None
    
    # Volume Analysis
    volume_sma: Optional[Decimal] = None
    volume_spike_detected: Optional[bool] = None
    volume_trend: Optional[str] = None
    
    # Validation Results
    validation_status: ValidationStatus = ValidationStatus.PENDING
    validation_score: Optional[Decimal] = None
    validation_reasons: List[str] = None
    priority_asset: bool = False
    
    # Risk Metrics
    volatility_24h: Optional[Decimal] = None
    market_cap_rank: Optional[int] = None
    risk_level: Optional[str] = None
    
    # Trading Signals
    signal_2h: Optional[str] = None
    signal_4h: Optional[str] = None
    signal_strength: Optional[Decimal] = None
    rules_triggered: List[str] = None
    
    # Metadata
    last_updated: Optional[datetime] = None
    data_quality_score: Optional[Decimal] = None
    api_response_time: Optional[float] = None
    
    def __post_init__(self):
        if self.validation_reasons is None:
            self.validation_reasons = []
        if self.rules_triggered is None:
            self.rules_triggered = []
        if self.last_updated is None:
            self.last_updated = datetime.utcnow()


class AssetValidationTable:
    """Comprehensive asset validation table with complete metrics collection."""
    
    def __init__(self):
        self.market_api = get_market_data_api()
        self.technical_indicators = get_technical_indicators()
        self.asset_validator = get_asset_validator()
        self.asset_repo = AssetRepository()
        self.config = TradingConfig()
        
        # Performance optimizations
        self.rate_limiter = get_rate_limiter()
        self.cache = get_smart_cache()
        
        # Legacy cache for backward compatibility
        self._market_data_cache = {}
        self._indicators_cache = {}
        
    async def collect_asset_metrics(self, symbol: str) -> AssetMetrics:
        """Collect complete metrics for a single asset."""
        start_time = datetime.utcnow()
        
        try:
            # Initialize metrics object
            base_currency, quote_currency = symbol.split('/')
            metrics = AssetMetrics(
                symbol=symbol,
                base_currency=base_currency,
                quote_currency=quote_currency
            )
            
            # Collect market data
            await self._collect_market_data(metrics)
            
            # Collect technical indicators
            await self._collect_technical_indicators(metrics)
            
            # Perform analysis
            await self._perform_analysis(metrics)
            
            # Run validation
            await self._run_validation(metrics)
            
            # Calculate performance metrics
            end_time = datetime.utcnow()
            metrics.api_response_time = (end_time - start_time).total_seconds()
            metrics.last_updated = end_time
            
            # Calculate data quality score
            metrics.data_quality_score = self._calculate_data_quality_score(metrics)
            
            logger.debug(f"Collected metrics for {symbol} in {metrics.api_response_time:.2f}s")
            return metrics
            
        except Exception as e:
            logger.error(f"Error collecting metrics for {symbol}: {e}")
            return AssetMetrics(
                symbol=symbol,
                base_currency=base_currency if '/' in symbol else '',
                quote_currency=quote_currency if '/' in symbol else '',
                validation_status=ValidationStatus.ERROR,
                validation_reasons=[f"Data collection error: {str(e)}"],
                last_updated=datetime.utcnow()
            )
    
    async def _collect_market_data(self, metrics: AssetMetrics) -> None:
        """Collect comprehensive market data with caching."""
        try:
            # Use cache to avoid redundant API calls
            market_summary = await self.cache.get_or_fetch(
                'market_summary', metrics.symbol,
                lambda: self._fetch_market_summary_with_rate_limit(metrics.symbol)
            )
            
            # Basic price data
            metrics.current_price = market_summary.get('price')
            metrics.price_change_24h = market_summary.get('change_24h')
            metrics.price_change_percent_24h = market_summary.get('change_percent_24h')
            
            # Volume data
            metrics.volume_24h_base = market_summary.get('volume_24h')
            metrics.volume_24h_quote = market_summary.get('quote_volume_24h')
            metrics.trades_count_24h = market_summary.get('trades_count_24h')
            
            # Liquidity data
            metrics.bid_price = market_summary.get('bid_price')
            metrics.ask_price = market_summary.get('ask_price')
            metrics.spread_percent = market_summary.get('spread_percent')
            
            # Volatility
            metrics.volatility_24h = market_summary.get('volatility_24h')
            
            # Calculate volume change if available (cached)
            volume_analysis = await self.cache.get_or_fetch(
                'volume_analysis', f"{metrics.symbol}_1h_24",
                lambda: self._fetch_volume_analysis_with_rate_limit(metrics.symbol, '1h', 24)
            )
            
            if volume_analysis:
                avg_volume = Decimal(str(volume_analysis.get('average_volume', 0)))
                current_volume = metrics.volume_24h_quote or Decimal('0')
                
                if avg_volume > 0:
                    volume_change = (current_volume - avg_volume) / avg_volume * 100
                    metrics.volume_change_percent = volume_change.quantize(Decimal('0.01'))
                
                # Store volume SMA
                metrics.volume_sma = avg_volume if avg_volume > 0 else None
                
                # Detect volume spike
                spike_threshold = Decimal('2.0')  # 200% of average
                metrics.volume_spike_detected = current_volume > (avg_volume * spike_threshold)
                
                # Volume trend
                if metrics.volume_change_percent:
                    if metrics.volume_change_percent > Decimal('20'):
                        metrics.volume_trend = "INCREASING"
                    elif metrics.volume_change_percent < Decimal('-20'):
                        metrics.volume_trend = "DECREASING"
                    else:
                        metrics.volume_trend = "STABLE"
            
        except Exception as e:
            logger.error(f"Error collecting market data for {metrics.symbol}: {e}")
            metrics.validation_reasons.append(f"Market data error: {str(e)}")
    
    async def _collect_technical_indicators(self, metrics: AssetMetrics) -> None:
        """Collect technical indicators for all timeframes with caching and parallel processing."""
        try:
            timeframes = ['spot', '2h', '4h']
            
            # Parallel fetch of candle data with caching
            candle_tasks = []
            for timeframe in timeframes:
                if timeframe == 'spot':
                    task = self.cache.get_or_fetch(
                        'candles', f"{metrics.symbol}_1m_50",
                        lambda tf=timeframe: self._fetch_candles_with_rate_limit(metrics.symbol, '1m', 50)
                    )
                else:
                    task = self.cache.get_or_fetch(
                        'candles', f"{metrics.symbol}_{timeframe}_50",
                        lambda tf=timeframe: self._fetch_candles_with_rate_limit(metrics.symbol, timeframe, 50)
                    )
                candle_tasks.append(task)
            
            # Execute candle fetching in parallel
            candle_results = await asyncio.gather(*candle_tasks, return_exceptions=True)
            
            # Process results for each timeframe
            for i, timeframe in enumerate(timeframes):
                try:
                    candles = candle_results[i]
                    if isinstance(candles, Exception) or not candles:
                        logger.warning(f"Failed to get candles for {metrics.symbol} {timeframe}: {candles if isinstance(candles, Exception) else 'No data'}")
                        continue
                    
                    # Calculate indicators (can be cached separately)
                    indicators = await self.cache.get_or_fetch(
                        'indicators', f"{metrics.symbol}_{timeframe}",
                        lambda: self.technical_indicators.calculate_all_indicators(candles)
                    )
                    
                    # Store by timeframe
                    if timeframe == 'spot':
                        metrics.mm1_spot = indicators.get('mm1')
                        metrics.center_spot = indicators.get('center')
                        metrics.rsi_spot = indicators.get('rsi')
                    elif timeframe == '2h':
                        metrics.mm1_2h = indicators.get('mm1')
                        metrics.center_2h = indicators.get('center')
                        metrics.rsi_2h = indicators.get('rsi')
                        
                        # Calculate MA distance and direction for 2h
                        if metrics.mm1_2h and metrics.center_2h:
                            distance = self.technical_indicators.calculate_ma_distance(
                                metrics.mm1_2h, metrics.center_2h
                            )
                            metrics.ma_distance_2h = distance
                            metrics.ma_direction_2h = "ABOVE" if metrics.mm1_2h > metrics.center_2h else "BELOW"
                        
                        # RSI condition for 2h
                        if metrics.rsi_2h:
                            metrics.rsi_condition_2h = self._get_rsi_condition(metrics.rsi_2h)
                    
                    elif timeframe == '4h':
                        metrics.mm1_4h = indicators.get('mm1')
                        metrics.center_4h = indicators.get('center')
                        metrics.rsi_4h = indicators.get('rsi')
                        
                        # Calculate MA distance and direction for 4h
                        if metrics.mm1_4h and metrics.center_4h:
                            distance = self.technical_indicators.calculate_ma_distance(
                                metrics.mm1_4h, metrics.center_4h
                            )
                            metrics.ma_distance_4h = distance
                            metrics.ma_direction_4h = "ABOVE" if metrics.mm1_4h > metrics.center_4h else "BELOW"
                        
                        # RSI condition for 4h
                        if metrics.rsi_4h:
                            metrics.rsi_condition_4h = self._get_rsi_condition(metrics.rsi_4h)
                
                except Exception as e:
                    logger.warning(f"Error calculating {timeframe} indicators for {metrics.symbol}: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Error collecting technical indicators for {metrics.symbol}: {e}")
            metrics.validation_reasons.append(f"Technical indicators error: {str(e)}")
    
    async def _perform_analysis(self, metrics: AssetMetrics) -> None:
        """Perform comprehensive analysis and generate signals."""
        try:
            # Generate trading signals for each timeframe
            signals_2h = self._generate_signals(metrics, '2h')
            signals_4h = self._generate_signals(metrics, '4h')
            
            metrics.signal_2h = signals_2h.get('signal')
            metrics.signal_4h = signals_4h.get('signal')
            
            # Combine signal strength
            strength_2h = signals_2h.get('strength', 0)
            strength_4h = signals_4h.get('strength', 0)
            metrics.signal_strength = max(strength_2h, strength_4h)
            
            # Collect triggered rules
            rules_2h = signals_2h.get('rules', [])
            rules_4h = signals_4h.get('rules', [])
            metrics.rules_triggered = list(set(rules_2h + rules_4h))
            
            # Determine risk level
            metrics.risk_level = self._calculate_risk_level(metrics)
            
            # Check if it's a priority asset
            from scanner.validator import ValidationCriteria
            criteria = ValidationCriteria()
            metrics.priority_asset = metrics.symbol in criteria.PRIORITY_SYMBOLS
            
        except Exception as e:
            logger.error(f"Error performing analysis for {metrics.symbol}: {e}")
            metrics.validation_reasons.append(f"Analysis error: {str(e)}")
    
    async def _run_validation(self, metrics: AssetMetrics) -> None:
        """Run comprehensive validation and assign status."""
        try:
            validation_result = await self.asset_validator.validate_asset(metrics.symbol)
            
            metrics.validation_status = ValidationStatus.VALID if validation_result['is_valid'] else ValidationStatus.INVALID
            
            if validation_result.get('reason'):
                metrics.validation_reasons.append(validation_result['reason'])
            
            # Calculate validation score (0-100)
            metrics.validation_score = self._calculate_validation_score(metrics)
            
        except Exception as e:
            logger.error(f"Error validating {metrics.symbol}: {e}")
            metrics.validation_status = ValidationStatus.ERROR
            metrics.validation_reasons.append(f"Validation error: {str(e)}")
    
    def _generate_signals(self, metrics: AssetMetrics, timeframe: str) -> Dict[str, Any]:
        """Generate trading signals for specific timeframe."""
        signal_info = {
            'signal': None,
            'strength': 0,
            'rules': []
        }
        
        try:
            if timeframe == '2h':
                mm1 = metrics.mm1_2h
                center = metrics.center_2h
                rsi = metrics.rsi_2h
                ma_distance = metrics.ma_distance_2h
                distance_threshold = Decimal('0.02')  # 2%
            elif timeframe == '4h':
                mm1 = metrics.mm1_4h
                center = metrics.center_4h
                rsi = metrics.rsi_4h
                ma_distance = metrics.ma_distance_4h
                distance_threshold = Decimal('0.03')  # 3%
            else:
                return signal_info
            
            if not all([mm1, center, rsi]):
                return signal_info
            
            rules_triggered = []
            strength = 0
            
            # Rule 1: MA Crossover + RSI
            if self.config.is_rsi_in_range(rsi):
                # Simplified crossover detection based on current position
                if mm1 > center:
                    rules_triggered.append(f"bullish_position_{timeframe}")
                    strength += 30
                elif mm1 < center:
                    rules_triggered.append(f"bearish_position_{timeframe}")
                    strength += 30
            
            # Rule 2: MA Distance
            if ma_distance and ma_distance >= distance_threshold:
                if mm1 > center:
                    rules_triggered.append(f"distance_bullish_{timeframe}")
                    strength += 40
                else:
                    rules_triggered.append(f"distance_bearish_{timeframe}")
                    strength += 40
            
            # Rule 3: Volume Spike
            if metrics.volume_spike_detected:
                if mm1 > center:
                    rules_triggered.append(f"volume_bullish_{timeframe}")
                    strength += 30
                elif mm1 < center:
                    rules_triggered.append(f"volume_bearish_{timeframe}")
                    strength += 30
            
            # Determine primary signal
            if strength >= 50:
                if mm1 > center:
                    signal_info['signal'] = "BUY"
                else:
                    signal_info['signal'] = "SELL"
            
            signal_info['strength'] = min(strength, 100)
            signal_info['rules'] = rules_triggered
            
        except Exception as e:
            logger.error(f"Error generating signals for {metrics.symbol} {timeframe}: {e}")
        
        return signal_info
    
    def _get_rsi_condition(self, rsi: Decimal) -> str:
        """Get RSI condition string."""
        if rsi <= 35:
            return "OVERSOLD"
        elif rsi >= 73:
            return "OVERBOUGHT"
        elif 35 < rsi < 73:
            return "NEUTRAL"
        else:
            return "EXTREME"
    
    def _calculate_risk_level(self, metrics: AssetMetrics) -> str:
        """Calculate risk level based on multiple factors."""
        try:
            risk_score = 0
            
            # Volatility risk
            if metrics.volatility_24h:
                if metrics.volatility_24h > 10:
                    risk_score += 3
                elif metrics.volatility_24h > 5:
                    risk_score += 2
                elif metrics.volatility_24h > 2:
                    risk_score += 1
            
            # Volume risk
            if metrics.volume_24h_quote:
                min_volume = self.config.MIN_VOLUME_24H_USDT
                if metrics.volume_24h_quote < min_volume * 2:
                    risk_score += 2
                elif metrics.volume_24h_quote < min_volume * 5:
                    risk_score += 1
            
            # Spread risk
            if metrics.spread_percent:
                if metrics.spread_percent > 1:
                    risk_score += 2
                elif metrics.spread_percent > 0.5:
                    risk_score += 1
            
            # Price risk
            if metrics.current_price:
                if metrics.current_price < Decimal('0.01'):
                    risk_score += 2
                elif metrics.current_price > Decimal('50000'):
                    risk_score += 1
            
            # Determine risk level
            if risk_score <= 2:
                return "LOW"
            elif risk_score <= 5:
                return "MEDIUM"
            else:
                return "HIGH"
            
        except Exception:
            return "UNKNOWN"
    
    def _calculate_validation_score(self, metrics: AssetMetrics) -> Decimal:
        """Calculate validation score (0-100) based on all factors."""
        try:
            score = 0
            max_score = 100
            
            # Basic validation (40 points)
            if metrics.validation_status == ValidationStatus.VALID:
                score += 40
            
            # Volume score (20 points)
            if metrics.volume_24h_quote:
                min_volume = self.config.MIN_VOLUME_24H_USDT
                if metrics.volume_24h_quote >= min_volume * 10:
                    score += 20
                elif metrics.volume_24h_quote >= min_volume * 5:
                    score += 15
                elif metrics.volume_24h_quote >= min_volume:
                    score += 10
            
            # Liquidity score (15 points)
            if metrics.spread_percent:
                if metrics.spread_percent <= 0.1:
                    score += 15
                elif metrics.spread_percent <= 0.5:
                    score += 10
                elif metrics.spread_percent <= 1.0:
                    score += 5
            
            # Technical indicators completeness (15 points)
            indicators_available = sum([
                1 for indicator in [
                    metrics.mm1_2h, metrics.center_2h, metrics.rsi_2h,
                    metrics.mm1_4h, metrics.center_4h, metrics.rsi_4h
                ] if indicator is not None
            ])
            score += int(indicators_available / 6 * 15)
            
            # Priority asset bonus (10 points)
            if metrics.priority_asset:
                score += 10
            
            return Decimal(str(min(score, max_score)))
            
        except Exception:
            return Decimal('0')
    
    def _calculate_data_quality_score(self, metrics: AssetMetrics) -> Decimal:
        """Calculate data quality score based on completeness."""
        try:
            total_fields = 0
            filled_fields = 0
            
            # Count all relevant fields
            for field_name, field_value in asdict(metrics).items():
                if field_name in ['validation_reasons', 'rules_triggered', 'last_updated']:
                    continue  # Skip list/metadata fields
                
                total_fields += 1
                if field_value is not None:
                    filled_fields += 1
            
            if total_fields == 0:
                return Decimal('0')
            
            quality_score = (filled_fields / total_fields) * 100
            return Decimal(str(round(quality_score, 1)))
            
        except Exception:
            return Decimal('0')
    
    async def _fetch_market_summary_with_rate_limit(self, symbol: str) -> Dict[str, Any]:
        """Fetch market summary with rate limiting."""
        await self.rate_limiter.acquire('market_data')
        return await self.market_api.get_market_summary(symbol)
    
    async def _fetch_volume_analysis_with_rate_limit(self, symbol: str, timeframe: str, periods: int) -> Dict[str, Any]:
        """Fetch volume analysis with rate limiting."""
        await self.rate_limiter.acquire('market_data')
        return await self.market_api.get_volume_analysis(symbol, timeframe, periods)
    
    async def _fetch_candles_with_rate_limit(self, symbol: str, timeframe: str, limit: int) -> List[Dict[str, Any]]:
        """Fetch candles with rate limiting."""
        await self.rate_limiter.acquire('market_data')
        return await self.market_api.get_candles(symbol, timeframe, limit)
    
    async def generate_validation_table(self, symbols: List[str], 
                                      max_concurrent: int = 20) -> List[AssetMetrics]:
        """Generate comprehensive validation table for multiple assets with optimized performance."""
        logger.info(f"Generating validation table for {len(symbols)} assets (optimized)")
        
        results = []
        
        # Optimized batch processing - larger batches, smarter rate limiting
        for i in range(0, len(symbols), max_concurrent):
            batch = symbols[i:i + max_concurrent]
            
            try:
                # Create tasks for concurrent processing
                tasks = [self.collect_asset_metrics(symbol) for symbol in batch]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process results
                for j, result in enumerate(batch_results):
                    if isinstance(result, Exception):
                        logger.error(f"Error processing {batch[j]}: {result}")
                        # Create error metrics
                        error_metrics = AssetMetrics(
                            symbol=batch[j],
                            base_currency="",
                            quote_currency="",
                            validation_status=ValidationStatus.ERROR,
                            validation_reasons=[f"Processing error: {str(result)}"]
                        )
                        results.append(error_metrics)
                    else:
                        results.append(result)
                
                logger.info(f"Completed batch {i//max_concurrent + 1}: {len(batch)} assets")
                
                # Intelligent rate limiting delay based on batch size and rate limiter stats
                if i + max_concurrent < len(symbols):
                    stats = self.rate_limiter.get_stats()
                    market_utilization = stats.get('market_data', {}).get('utilization_percent', 0)
                    
                    # Adaptive delay: less delay if utilization is low
                    if market_utilization < 60:
                        delay = 0.2  # Aggressive - use more of available capacity
                    elif market_utilization < 80:
                        delay = 0.5  # Moderate delay
                    else:
                        delay = 1.0  # Conservative delay
                    
                    await asyncio.sleep(delay)
                    
            except Exception as e:
                logger.error(f"Error processing batch starting at index {i}: {e}")
                
                # Create error results for failed batch
                for symbol in batch:
                    error_metrics = AssetMetrics(
                        symbol=symbol,
                        base_currency="",
                        quote_currency="",
                        validation_status=ValidationStatus.ERROR,
                        validation_reasons=[f"Batch error: {str(e)}"]
                    )
                    results.append(error_metrics)
        
        # Sort results by validation score (highest first)
        results.sort(key=lambda x: x.validation_score or Decimal('0'), reverse=True)
        
        # Log performance stats
        cache_stats = self.cache.get_stats()
        rate_stats = self.rate_limiter.get_stats()
        
        logger.info(f"Validation table generated: {len(results)} assets processed")
        logger.info(f"Cache performance: {cache_stats['hit_rate_percent']}% hit rate, {cache_stats['hits']} hits, {cache_stats['misses']} misses")
        logger.info(f"Rate limiting: Market data {rate_stats.get('market_data', {}).get('utilization_percent', 0):.1f}% utilization")
        
        return results
    
    def format_table_for_display(self, metrics_list: List[AssetMetrics]) -> str:
        """Format validation table for console display."""
        try:
            if not metrics_list:
                return "No assets to display."
            
            # Table header
            header = (
                f"{'Symbol':<12} {'Status':<8} {'Score':<6} {'Price':<12} {'Vol(24h)':<12} "
                f"{'Spread%':<8} {'RSI(2h)':<8} {'RSI(4h)':<8} {'Signal':<6} {'Risk':<6} "
                f"{'Updated':<19}"
            )
            
            separator = "=" * len(header)
            
            rows = [separator, header, separator]
            
            # Format each asset
            for metrics in metrics_list:
                # Format price
                price_str = PriceFormatter.format_price(metrics.current_price) if metrics.current_price else "N/A"
                
                # Format volume
                vol_str = PriceFormatter.format_volume(metrics.volume_24h_quote) if metrics.volume_24h_quote else "N/A"
                
                # Format spread
                spread_str = f"{metrics.spread_percent:.3f}" if metrics.spread_percent else "N/A"
                
                # Format RSI values
                rsi_2h_str = f"{metrics.rsi_2h:.1f}" if metrics.rsi_2h else "N/A"
                rsi_4h_str = f"{metrics.rsi_4h:.1f}" if metrics.rsi_4h else "N/A"
                
                # Primary signal
                signal = metrics.signal_2h or metrics.signal_4h or "NONE"
                
                # Format timestamp
                updated_str = metrics.last_updated.strftime("%Y-%m-%d %H:%M:%S") if metrics.last_updated else "N/A"
                
                row = (
                    f"{metrics.symbol:<12} {metrics.validation_status.value:<8} "
                    f"{metrics.validation_score or 0:<6.0f} {price_str:<12} {vol_str:<12} "
                    f"{spread_str:<8} {rsi_2h_str:<8} {rsi_4h_str:<8} {signal:<6} "
                    f"{metrics.risk_level or 'N/A':<6} {updated_str:<19}"
                )
                
                rows.append(row)
            
            rows.append(separator)
            
            # Add summary
            total_assets = len(metrics_list)
            valid_assets = len([m for m in metrics_list if m.validation_status == ValidationStatus.VALID])
            priority_assets = len([m for m in metrics_list if m.priority_asset])
            
            summary = (
                f"\nSummary: {valid_assets}/{total_assets} valid assets "
                f"({priority_assets} priority assets)"
            )
            
            rows.append(summary)
            
            return "\n".join(rows)
            
        except Exception as e:
            logger.error(f"Error formatting table: {e}")
            return f"Error formatting table: {str(e)}"


# Global asset validation table instance
_asset_validation_table = None


def get_asset_validation_table() -> AssetValidationTable:
    """Get the global AssetValidationTable instance."""
    global _asset_validation_table
    if _asset_validation_table is None:
        _asset_validation_table = AssetValidationTable()
    return _asset_validation_table


# Convenience function for quick table generation
async def generate_asset_validation_report(symbols: List[str] = None, 
                                         max_concurrent: int = 10) -> str:
    """Generate and format complete asset validation report."""
    try:
        table = get_asset_validation_table()
        
        # Use default symbols if not provided
        if symbols is None:
            from scanner.validator import ValidationCriteria
            criteria = ValidationCriteria()
            symbols = criteria.PRIORITY_SYMBOLS[:20]  # Top 20 priority assets
        
        # Generate metrics
        metrics_list = await table.generate_validation_table(symbols, max_concurrent)
        
        # Format for display
        formatted_table = table.format_table_for_display(metrics_list)
        
        return formatted_table
        
    except Exception as e:
        logger.error(f"Error generating validation report: {e}")
        return f"Error generating validation report: {str(e)}"