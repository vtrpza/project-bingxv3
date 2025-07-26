# trading/symbol_selector.py
"""
Autonomous symbol selector for trading system.
Selects symbols based on trading-specific criteria, independent of scanner.
"""

import asyncio
import logging
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from api.market_data import get_market_data_api
from utils.logger import get_logger
from utils.datetime_utils import utc_now

logger = get_logger(__name__)


@dataclass
class TradingSymbol:
    """Container for a symbol selected for trading."""
    symbol: str
    volume_24h: float
    spread_percent: float
    volatility_24h: float
    liquidity_score: float
    selection_score: float
    selection_reasons: List[str] = field(default_factory=list)
    selected_at: datetime = field(default_factory=utc_now)
    last_checked: datetime = field(default_factory=utc_now)
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'volume_24h': self.volume_24h,
            'spread_percent': self.spread_percent,
            'volatility_24h': self.volatility_24h,
            'liquidity_score': self.liquidity_score,
            'selection_score': self.selection_score,
            'selection_reasons': self.selection_reasons,
            'selected_at': self.selected_at.isoformat(),
            'last_checked': self.last_checked.isoformat()
        }


class SymbolSelector:
    """
    Selects symbols for trading based on specific criteria.
    Independent from the scanner system.
    """
    
    def __init__(self):
        self.market_api = get_market_data_api()
        
        # Selection criteria thresholds - PRODUCTION READY FOR ALL VALID SYMBOLS
        self.MIN_VOLUME_24H_USDT = 10000  # $10K minimum daily volume (production ready)
        self.MAX_SPREAD_PERCENT = 2.0  # 2% maximum spread (reasonable for trading)
        self.MIN_VOLATILITY_24H = 0.1  # 0.1% minimum daily volatility (avoid dead markets)
        self.MAX_VOLATILITY_24H = 50.0  # 50% maximum daily volatility (avoid extreme volatility)
        self.MIN_LIQUIDITY_SCORE = 0.1  # Minimum liquidity score (ensure tradeable)
        
        # Process ALL valid symbols - no arbitrary limits
        self.MAX_TRADING_SYMBOLS = None  # No limit - process all valid symbols
        
        # Individual symbol cache with TTL per symbol
        self.symbol_cache = {}  # symbol -> {data, timestamp}
        self.selected_symbols_cache = {}  # symbol -> TradingSymbol
        self.cache_timestamp = None
        self.SYMBOL_CACHE_TTL = 60  # 60 seconds cache per symbol
        self.SELECTION_CACHE_TTL = 300  # 5 minutes cache for full selection
        
        logger.info(f"SymbolSelector initialized with criteria: "
                   f"Volume>${self.MIN_VOLUME_24H_USDT}, "
                   f"Spread<{self.MAX_SPREAD_PERCENT}%, "
                   f"Volatility {self.MIN_VOLATILITY_24H}-{self.MAX_VOLATILITY_24H}%")
    
    async def select_trading_symbols(self, force_refresh: bool = False) -> List[TradingSymbol]:
        """
        Select symbols for trading based on current market conditions.
        Uses efficient batch operations to avoid rate limiting.
        
        Returns:
            List of TradingSymbol objects that meet all criteria
        """
        try:
            logger.info("🎯 Starting efficient trading symbol selection process...")
            
            # Step 1: Get all available USDT markets
            markets = await self._get_usdt_markets(force_refresh)
            logger.info(f"Found {len(markets)} USDT markets to evaluate")
            
            if not markets:
                logger.warning("No markets found for symbol selection")
                return []
            
            # Step 2: Extract valid symbols and filter using validation
            from utils.validators import Validator
            
            valid_symbols = []
            for market in markets:
                symbol = market.get('symbol', '')
                if symbol and symbol.endswith('USDT') and Validator.is_valid_symbol(symbol):
                    valid_symbols.append(symbol)
            
            logger.info(f"Pre-filtered to {len(valid_symbols)} valid USDT symbols")
            
            if not valid_symbols:
                logger.warning("No valid symbols found after filtering")
                return []
            
            # Step 3: Ultra-efficient symbol selection without static data
            # Be extremely selective to avoid rate limits
            logger.info("🎯 Ultra-efficient symbol selection process...")
            
            # Strategy: Process only the most liquid and active symbols
            # This ensures we get quality trading symbols without hitting rate limits
            
            # Define high-liquidity base currencies (no static fallback - based on market knowledge)
            high_liquidity_bases = {
                'BTC', 'ETH', 'BNB', 'XRP', 'ADA', 'SOL', 'DOT', 'DOGE', 'AVAX', 'MATIC',
                'LINK', 'UNI', 'ATOM', 'LTC', 'BCH', 'ALGO', 'VET', 'ICP', 'FIL', 'TRX',
                'AAVE', 'SUSHI', 'COMP', 'MKR', 'SNX', 'YFI', 'CRV', 'SAND', 'MANA', 'AXS'
            }
            
            # Filter to only high-liquidity pairs
            high_liquidity_symbols = []
            for symbol in valid_symbols:
                try:
                    base = symbol.split('/')[0]
                    if base in high_liquidity_bases:
                        high_liquidity_symbols.append(symbol)
                except:
                    continue
            
            # Be EXTREMELY conservative - process only top 10 symbols to avoid rate limits
            max_symbols_to_process = 10
            selected_symbols_for_api = high_liquidity_symbols[:max_symbols_to_process]
            
            if not selected_symbols_for_api:
                logger.warning("No high-liquidity symbols found - taking first 10 available")
                selected_symbols_for_api = valid_symbols[:max_symbols_to_process]
            
            logger.info(f"🎯 Processing ONLY {len(selected_symbols_for_api)} TOP symbols for efficiency")
            logger.info(f"📊 Symbols to check: {', '.join(selected_symbols_for_api[:5])}{'...' if len(selected_symbols_for_api) > 5 else ''}")
            
            # Batch fetch ticker data with controlled rate
            try:
                tickers_data = await self.market_api.get_multiple_tickers(selected_symbols_for_api)
            except Exception as e:
                logger.error(f"❌ Failed to fetch ticker data: {e}")
                logger.warning("Symbol selection cannot proceed without ticker data")
                return []
            
            if not tickers_data:
                logger.warning("❌ No ticker data received from batch fetch - API may be unavailable")
                return []
            
            logger.info(f"✅ Successfully fetched ticker data for {len(tickers_data)} symbols")
            
            # Step 4: Evaluate all symbols using pre-fetched ticker data
            all_valid_symbols = []
            evaluated_count = 0
            
            for symbol, ticker in tickers_data.items():
                if not ticker:
                    continue
                
                # Evaluate symbol using pre-fetched ticker data (optimized - no market_data needed)
                trading_symbol = self._evaluate_symbol_with_ticker(symbol, ticker)
                
                if trading_symbol:
                    all_valid_symbols.append(trading_symbol)
                    logger.debug(f"✅ Selected {symbol} for trading (score: {trading_symbol.selection_score:.2f})")
                
                evaluated_count += 1
            
            # Step 5: Sort by selection score (no arbitrary limit)
            all_valid_symbols.sort(key=lambda x: x.selection_score, reverse=True)
            
            logger.info(f"🎯 Efficient symbol selection complete: "
                       f"{len(all_valid_symbols)}/{evaluated_count} symbols selected")
            
            # Log selection summary
            self._log_selection_summary(all_valid_symbols)
            
            return all_valid_symbols
            
        except Exception as e:
            logger.error(f"Error in symbol selection: {e}")
            return []
    
    async def _get_usdt_markets(self, force_refresh: bool) -> List[Dict]:
        """Get all USDT trading pairs from exchange."""
        try:
            markets = await self.market_api.get_usdt_markets(force_refresh)
            # Filter active markets only
            return [m for m in markets if m.get('active', False)]
        except Exception as e:
            logger.error(f"Error fetching markets: {e}")
            return []
    
    def _evaluate_symbol_with_ticker(self, symbol: str, ticker: Dict, market_data: Dict = None) -> Optional[TradingSymbol]:
        """
        Evaluate a single symbol against trading criteria using pre-fetched ticker data.
        Optimized for batch processing without individual API calls.
        
        Args:
            symbol: Trading symbol (e.g., 'BTC/USDT')
            ticker: Pre-fetched ticker data from batch operation
            market_data: Market metadata (unused - maintained for compatibility)
        
        Returns:
            TradingSymbol if all criteria met, None otherwise
        """
        try:
            # Validate ticker data structure first
            if not ticker or not isinstance(ticker, dict):
                logger.debug(f"❌ Invalid ticker data structure for {symbol}")
                return None
            
            # Extract metrics from pre-fetched ticker data with robust error handling
            try:
                volume_24h = float(ticker.get('quoteVolume', 0))  # Volume in USDT
                bid = float(ticker.get('bid', 0))
                ask = float(ticker.get('ask', 0))
                high_24h = float(ticker.get('high', 0))
                low_24h = float(ticker.get('low', 0))
                last_price = float(ticker.get('last', 0))
            except (ValueError, TypeError) as e:
                logger.debug(f"❌ Error parsing ticker data for {symbol}: {e}")
                return None
            
            # Skip if basic data is missing or invalid
            if not last_price or last_price <= 0:
                logger.debug(f"❌ Invalid or missing price data for {symbol}: {last_price}")
                return None
            
            # Calculate metrics - use safe defaults if data missing
            spread_percent = ((ask - bid) / last_price) * 100 if (bid > 0 and ask > 0 and last_price > 0) else 0.1
            volatility_24h = ((high_24h - low_24h) / last_price) * 100 if (high_24h > 0 and low_24h > 0 and last_price > 0) else 1.0
            
            # Calculate liquidity score (0-1)
            liquidity_score = self._calculate_liquidity_score(volume_24h, spread_percent)
            
            # Apply strict production criteria for quality trading symbols
            selection_reasons = []
            selection_score = 0.0
            meets_criteria = True
            
            # Volume check (weight: 30%) - STRICT REQUIREMENT
            if volume_24h >= self.MIN_VOLUME_24H_USDT:
                selection_reasons.append(f"Volume: ${volume_24h:,.0f}")
                # Score based on volume tier (logarithmic scale)
                volume_multiplier = min(volume_24h / self.MIN_VOLUME_24H_USDT, 100)
                selection_score += 0.3 * min(1.0, 0.3 + 0.7 * (volume_multiplier / 100))
            else:
                meets_criteria = False
                logger.debug(f"❌ {symbol} rejected: Volume ${volume_24h:,.0f} < ${self.MIN_VOLUME_24H_USDT:,.0f}")
                return None
            
            # Spread check (weight: 25%) - STRICT REQUIREMENT
            if spread_percent <= self.MAX_SPREAD_PERCENT:
                selection_reasons.append(f"Spread: {spread_percent:.3f}%")
                # Better spread = higher score
                selection_score += 0.25 * (1 - spread_percent / self.MAX_SPREAD_PERCENT)
            else:
                meets_criteria = False
                logger.debug(f"❌ {symbol} rejected: Spread {spread_percent:.3f}% > {self.MAX_SPREAD_PERCENT}%")
                return None
            
            # Volatility check (weight: 25%) - STRICT REQUIREMENT
            if self.MIN_VOLATILITY_24H <= volatility_24h <= self.MAX_VOLATILITY_24H:
                selection_reasons.append(f"Volatility: {volatility_24h:.2f}%")
                # Prefer moderate volatility (optimal range 2-8%)
                optimal_min, optimal_max = 2.0, 8.0
                if optimal_min <= volatility_24h <= optimal_max:
                    # Peak score for optimal range
                    selection_score += 0.25
                else:
                    # Reduced score for suboptimal but acceptable range
                    if volatility_24h < optimal_min:
                        ratio = volatility_24h / optimal_min
                    else:
                        ratio = optimal_max / volatility_24h
                    selection_score += 0.25 * ratio
            else:
                meets_criteria = False
                logger.debug(f"❌ {symbol} rejected: Volatility {volatility_24h:.2f}% not in range {self.MIN_VOLATILITY_24H}-{self.MAX_VOLATILITY_24H}%")
                return None
            
            # Liquidity check (weight: 20%) - STRICT REQUIREMENT
            if liquidity_score >= self.MIN_LIQUIDITY_SCORE:
                selection_reasons.append(f"Liquidity: {liquidity_score:.2f}")
                selection_score += 0.2 * liquidity_score
            else:
                meets_criteria = False
                logger.debug(f"❌ {symbol} rejected: Liquidity {liquidity_score:.2f} < {self.MIN_LIQUIDITY_SCORE}")
                return None
            
            # Only create trading symbol if ALL criteria are met
            if meets_criteria:
                return TradingSymbol(
                    symbol=symbol,
                    volume_24h=volume_24h,
                    spread_percent=spread_percent,
                    volatility_24h=volatility_24h,
                    liquidity_score=liquidity_score,
                    selection_score=selection_score,
                    selection_reasons=selection_reasons
                )
            else:
                return None
            
        except Exception as e:
            logger.debug(f"Error evaluating {symbol}: {e}")
            return None
    
    
    def _calculate_liquidity_score(self, volume_24h: float, spread_percent: float) -> float:
        """
        Calculate liquidity score (0-1) based on volume and spread.
        Higher volume and lower spread = better liquidity.
        """
        # Volume score (0-1)
        volume_score = min(volume_24h / 10_000_000, 1.0)  # Max at $10M
        
        # Spread score (0-1) 
        spread_score = max(0, 1 - spread_percent / 1.0)  # 0% = 1.0, 1% = 0.0
        
        # Combined score (weighted average)
        liquidity_score = (volume_score * 0.7) + (spread_score * 0.3)
        
        return liquidity_score
    
    def _log_selection_summary(self, selected_symbols: List[TradingSymbol]):
        """Log summary of selected symbols."""
        if not selected_symbols:
            logger.warning("No symbols selected for trading")
            return
        
        logger.info("=" * 60)
        logger.info("TRADING SYMBOL SELECTION SUMMARY")
        logger.info("=" * 60)
        
        # Top 10 by score
        logger.info("\nTop 10 Selected Symbols:")
        for i, sym in enumerate(selected_symbols[:10], 1):
            logger.info(f"{i}. {sym.symbol} - Score: {sym.selection_score:.2f} - "
                       f"Volume: ${sym.volume_24h:,.0f} - "
                       f"Spread: {sym.spread_percent:.3f}% - "
                       f"Vol24h: {sym.volatility_24h:.2f}%")
        
        # Statistics
        avg_volume = sum(s.volume_24h for s in selected_symbols) / len(selected_symbols)
        avg_spread = sum(s.spread_percent for s in selected_symbols) / len(selected_symbols)
        avg_volatility = sum(s.volatility_24h for s in selected_symbols) / len(selected_symbols)
        
        logger.info(f"\nSelection Statistics:")
        logger.info(f"Total symbols selected: {len(selected_symbols)}")
        logger.info(f"Average 24h volume: ${avg_volume:,.0f}")
        logger.info(f"Average spread: {avg_spread:.3f}%")
        logger.info(f"Average 24h volatility: {avg_volatility:.2f}%")
        logger.info("=" * 60)


    async def get_all_valid_symbols_async(self) -> List[TradingSymbol]:
        """Get all valid trading symbols using real API data - ASYNC VERSION"""
        try:
            # Use real symbol selection (not mock)
            return await self.select_trading_symbols(force_refresh=False)
        except Exception as e:
            logger.error(f"Error getting all valid symbols: {e}")
            return []
    
    def get_selected_symbols_with_data(self, limit: int = None) -> Dict[str, Any]:
        """Get selected symbols with their analysis data for frontend - REAL DATA VERSION"""
        current_time = utc_now()
        
        # Check cache validity
        if (self.cache_timestamp and 
            (current_time - self.cache_timestamp).total_seconds() < self.SELECTION_CACHE_TTL and
            self.selected_symbols_cache):
            # Return cached data (respecting limit if provided)
            cached_data = self.selected_symbols_cache
            if limit:
                cached_data = dict(list(cached_data.items())[:limit])
            logger.info(f"Returning cached symbol data ({len(cached_data)} symbols)")
            return cached_data
        
        try:
            # Get real trading symbols asynchronously in a synchronous context
            import asyncio
            import concurrent.futures
            
            def run_async_selection():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    return loop.run_until_complete(self.get_all_valid_symbols_async())
                finally:
                    loop.close()
            
            # Run in thread pool to avoid blocking
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_async_selection)
                try:
                    selected_symbols = future.result(timeout=60)  # 60 second timeout for large datasets
                except concurrent.futures.TimeoutError:
                    logger.error("⏰ Symbol selection timed out - API response too slow")
                    selected_symbols = []
                except Exception as e:
                    logger.error(f"❌ Error during symbol selection execution: {e}")
                    selected_symbols = []
            
            if not selected_symbols:
                logger.warning("No symbols selected by trading selector - cannot proceed without API data")
                return {}
            
            # Format data for frontend
            formatted_data = {}
            symbols_to_process = selected_symbols[:limit] if limit else selected_symbols
            
            for trading_symbol in symbols_to_process:
                symbol = trading_symbol.symbol
                # Get real analysis data
                try:
                    from analysis.signals import SignalGenerator
                    signal_gen = SignalGenerator()
                    
                    # Get real indicators and signals
                    analysis_result = signal_gen.generate_signal_sync(symbol)
                    
                    if analysis_result:
                        formatted_data[symbol] = {
                            'score': trading_symbol.selection_score,
                            'volume_24h': trading_symbol.volume_24h,
                            'spread_percent': trading_symbol.spread_percent,
                            'volatility_24h': trading_symbol.volatility_24h,
                            'liquidity_score': trading_symbol.liquidity_score,
                            'selection_reasons': trading_symbol.selection_reasons,
                            'signal': analysis_result.get('signal', 'NEUTRAL'),
                            'spot': analysis_result.get('indicators', {}).get('spot', {}),
                            '2h': analysis_result.get('indicators', {}).get('2h', {}),
                            '4h': analysis_result.get('indicators', {}).get('4h', {}),
                            'analysis': {
                                'timestamp': current_time.isoformat(),
                                'selected_at': trading_symbol.selected_at.isoformat(),
                                'signal_strength': analysis_result.get('signal_strength', 0),
                                'rules_triggered': analysis_result.get('rules_triggered', [])
                            }
                        }
                    else:
                        # Fallback to basic data if analysis fails
                        formatted_data[symbol] = {
                            'score': trading_symbol.selection_score,
                            'volume_24h': trading_symbol.volume_24h,
                            'signal': 'NEUTRAL',
                            'spot': {},
                            '2h': {},
                            '4h': {},
                            'analysis': {
                                'timestamp': current_time.isoformat(),
                                'error': 'Analysis unavailable'
                            }
                        }
                except Exception as e:
                    logger.error(f"Error getting analysis for {symbol}: {e}")
                    # Basic fallback
                    formatted_data[symbol] = {
                        'score': trading_symbol.selection_score,
                        'signal': 'NEUTRAL',
                        'analysis': {'error': str(e)}
                    }
            
            # Update cache
            self.selected_symbols_cache = formatted_data
            self.cache_timestamp = current_time
            
            logger.info(f"✅ Formatted {len(formatted_data)} symbols for frontend (real data)")
            return formatted_data
            
        except Exception as e:
            logger.error(f"Error getting selected symbols data: {e}")
            # Return empty dict if API fails - no static fallbacks
            logger.warning("Symbol selection failed - cannot proceed without API data")
            return {}
    


# Global instance
_symbol_selector: Optional[SymbolSelector] = None


def get_symbol_selector() -> SymbolSelector:
    """Get or create global symbol selector instance."""
    global _symbol_selector
    if _symbol_selector is None:
        _symbol_selector = SymbolSelector()
    return _symbol_selector