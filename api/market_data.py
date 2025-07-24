# api/market_data.py
"""Market data API functionality for BingX."""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from .client import get_client, MarketDataError
from utils.logger import get_logger, performance_logger
from utils.validators import Validator, ValidationError
from utils.formatters import PriceFormatter
from config.trading_config import TradingConfig

logger = get_logger(__name__)
perf_logger = performance_logger


class MarketDataAPI:
    """Market data API wrapper for BingX exchange."""
    
    def __init__(self):
        self.client = get_client()
        self._market_cache = {}
        self._cache_ttl = 300  # 5 minutes
        self._last_market_fetch = None
        self._initialization_attempted = False
    
    async def _ensure_client_initialized(self):
        """Ensure the client is initialized before making API calls."""
        if not self.client._initialized and not self._initialization_attempted:
            self._initialization_attempted = True
            try:
                logger.info("Initializing BingX client...")
                success = await self.client.initialize()
                if not success:
                    logger.error("Failed to initialize BingX client")
                    # For demo purposes, create a mock client if initialization fails
                    from .client import BingXError
                    raise BingXError("BingX client initialization failed")
                else:
                    logger.info("BingX client initialized successfully")
            except Exception as e:
                logger.error(f"Error during client initialization: {e}")
                # For development/demo, continue without throwing error
                # In production, you might want to raise the error
                pass
    
    async def get_usdt_markets(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Get all USDT trading pairs with caching."""
        await self._ensure_client_initialized()
        
        current_time = datetime.utcnow()
        
        # Check cache validity
        if (not force_refresh and 
            self._market_cache and 
            self._last_market_fetch and
            (current_time - self._last_market_fetch).seconds < self._cache_ttl):
            logger.debug("Returning cached USDT markets")
            return self._market_cache
        
        try:
            start_time = asyncio.get_event_loop().time()
            markets = await self.client.fetch_markets()
            duration = asyncio.get_event_loop().time() - start_time
            
            perf_logger.execution_time("fetch_markets", duration)
            
            # Filter and enhance market data
            enhanced_markets = []
            for market in markets:
                if market['quote'] == 'USDT' and market['active']:
                    enhanced_markets.append({
                        **market,
                        'min_order_size': self._get_min_order_size(market),
                        'price_precision': self._get_price_precision(market),
                        'quantity_precision': self._get_quantity_precision(market),
                    })
            
            # Update cache
            self._market_cache = enhanced_markets
            self._last_market_fetch = current_time
            
            logger.info(f"Fetched {len(enhanced_markets)} USDT markets")
            return enhanced_markets
            
        except Exception as e:
            logger.error(f"Error fetching USDT markets: {e}")
            raise MarketDataError(f"Failed to fetch USDT markets: {e}")
    
    def _get_min_order_size(self, market: Dict[str, Any]) -> Decimal:
        """Extract minimum order size from market limits."""
        try:
            limits = market.get('limits', {})
            amount_limits = limits.get('amount', {})
            cost_limits = limits.get('cost', {})
            
            # Use the higher of minimum amount or cost-based minimum
            min_amount = Decimal(str(amount_limits.get('min', 0)))
            min_cost = Decimal(str(cost_limits.get('min', 0)))
            
            return max(min_amount, min_cost, TradingConfig.MIN_ORDER_SIZE_USDT)
        except Exception:
            return TradingConfig.MIN_ORDER_SIZE_USDT
    
    def _get_price_precision(self, market: Dict[str, Any]) -> int:
        """Extract price precision from market data."""
        try:
            precision = market.get('precision', {})
            return int(precision.get('price', 8))
        except Exception:
            return 8
    
    def _get_quantity_precision(self, market: Dict[str, Any]) -> int:
        """Extract quantity precision from market data."""
        try:
            precision = market.get('precision', {})
            return int(precision.get('amount', 6))
        except Exception:
            return 6
    
    async def get_current_price(self, symbol: str) -> Decimal:
        """Get current price for a symbol."""
        await self._ensure_client_initialized()
        
        if not Validator.is_valid_symbol(symbol):
            raise ValidationError(f"Invalid symbol: {symbol}")
        
        try:
            start_time = asyncio.get_event_loop().time()
            ticker = await self.client.fetch_ticker(symbol)
            duration = asyncio.get_event_loop().time() - start_time
            
            perf_logger.execution_time("fetch_ticker", duration)
            
            return ticker['last']
            
        except Exception as e:
            logger.error(f"Error fetching current price for {symbol}: {e}")
            raise MarketDataError(f"Failed to fetch current price for {symbol}: {e}")
    
    async def get_market_summary(self, symbol: str) -> Dict[str, Any]:
        """Get comprehensive market summary for a symbol."""
        await self._ensure_client_initialized()
        
        if not Validator.is_valid_symbol(symbol):
            raise ValidationError(f"Invalid symbol: {symbol}")
        
        try:
            start_time = asyncio.get_event_loop().time()
            ticker = await self.client.fetch_ticker(symbol)
            duration = asyncio.get_event_loop().time() - start_time
            
            perf_logger.execution_time("fetch_market_summary", duration)
            
            return {
                'symbol': symbol,
                'price': ticker['last'],
                'bid': ticker['bid'],
                'ask': ticker['ask'],
                'spread': ticker['ask'] - ticker['bid'] if ticker['ask'] and ticker['bid'] else None,
                'spread_percent': ((ticker['ask'] - ticker['bid']) / ticker['last'] * 100) if ticker['ask'] and ticker['bid'] and ticker['last'] else None,
                'volume_24h': ticker['volume'],
                'quote_volume_24h': ticker['quote_volume'],
                'change_24h': ticker['change'],
                'change_percent_24h': ticker['percentage'],
                'high_24h': ticker['high'],
                'low_24h': ticker['low'],
                'open_24h': ticker['open'],
                'timestamp': ticker['timestamp'],
                'datetime': ticker['datetime'],
            }
            
        except Exception as e:
            logger.error(f"Error fetching market summary for {symbol}: {e}")
            raise MarketDataError(f"Failed to fetch market summary for {symbol}: {e}")
    
    async def get_candles(self, symbol: str, timeframe: str = '1h', 
                         limit: int = 100, since: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get candlestick data for a symbol."""
        await self._ensure_client_initialized()
        
        if not Validator.is_valid_symbol(symbol):
            raise ValidationError(f"Invalid symbol: {symbol}")
        
        if not Validator.is_valid_timeframe(timeframe):
            raise ValidationError(f"Invalid timeframe: {timeframe}")
        
        try:
            since_timestamp = None
            if since:
                since_timestamp = int(since.timestamp() * 1000)
            
            start_time = asyncio.get_event_loop().time()
            candles = await self.client.fetch_ohlcv(symbol, timeframe, limit, since_timestamp)
            duration = asyncio.get_event_loop().time() - start_time
            
            perf_logger.execution_time("fetch_ohlcv", duration, {
                "symbol": symbol,
                "timeframe": timeframe,
                "candles_count": len(candles)
            })
            
            logger.debug(f"Fetched {len(candles)} candles for {symbol} {timeframe}")
            return candles
            
        except Exception as e:
            logger.error(f"Error fetching candles for {symbol} {timeframe}: {e}")
            raise MarketDataError(f"Failed to fetch candles for {symbol} {timeframe}: {e}")
    
    async def get_recent_candles(self, symbol: str, timeframe: str = '1h', 
                                hours_back: int = 24) -> List[Dict[str, Any]]:
        """Get recent candlestick data for specified hours back."""
        since = datetime.utcnow() - timedelta(hours=hours_back)
        return await self.get_candles(symbol, timeframe, since=since)
    
    async def get_multiple_tickers(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get tickers for multiple symbols concurrently."""
        valid_symbols = []
        for symbol in symbols:
            if Validator.is_valid_symbol(symbol):
                valid_symbols.append(symbol)
            else:
                logger.warning(f"Skipping invalid symbol: {symbol}")
        
        if not valid_symbols:
            return {}
        
        try:
            start_time = asyncio.get_event_loop().time()
            
            # Fetch tickers concurrently
            tasks = [self.client.fetch_ticker(symbol) for symbol in valid_symbols]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            duration = asyncio.get_event_loop().time() - start_time
            perf_logger.execution_time("fetch_multiple_tickers", duration, {
                "symbols_count": len(valid_symbols)
            })
            
            # Process results
            tickers = {}
            for i, result in enumerate(results):
                symbol = valid_symbols[i]
                if isinstance(result, Exception):
                    logger.error(f"Error fetching ticker for {symbol}: {result}")
                else:
                    tickers[symbol] = result
            
            logger.info(f"Fetched tickers for {len(tickers)}/{len(valid_symbols)} symbols")
            return tickers
            
        except Exception as e:
            logger.error(f"Error fetching multiple tickers: {e}")
            raise MarketDataError(f"Failed to fetch multiple tickers: {e}")
    
    async def get_volume_analysis(self, symbol: str, timeframe: str = '1h', 
                                 periods: int = 20) -> Dict[str, Any]:
        """Get volume analysis for a symbol."""
        try:
            candles = await self.get_candles(symbol, timeframe, limit=periods + 1)
            
            if len(candles) < periods:
                raise MarketDataError(f"Insufficient data for volume analysis: {len(candles)} < {periods}")
            
            # Calculate volume statistics
            volumes = [candle['volume'] for candle in candles]
            current_volume = volumes[-1]
            historical_volumes = volumes[:-1]
            
            avg_volume = sum(historical_volumes) / len(historical_volumes)
            max_volume = max(historical_volumes)
            min_volume = min(historical_volumes)
            
            # Volume spike detection
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
            is_volume_spike = TradingConfig.is_volume_spike(current_volume, avg_volume)
            
            return {
                'symbol': symbol,
                'timeframe': timeframe,
                'current_volume': current_volume,
                'average_volume': avg_volume,
                'max_volume': max_volume,
                'min_volume': min_volume,
                'volume_ratio': volume_ratio,
                'is_spike': is_volume_spike,
                'spike_threshold': TradingConfig.VOLUME_SPIKE_THRESHOLD,
                'periods_analyzed': len(historical_volumes),
            }
            
        except Exception as e:
            logger.error(f"Error analyzing volume for {symbol}: {e}")
            raise MarketDataError(f"Failed to analyze volume for {symbol}: {e}")
    
    async def get_orderbook(self, symbol: str, depth: int = 20) -> Dict[str, Any]:
        """Get order book data for a symbol."""
        if not Validator.is_valid_symbol(symbol):
            raise ValidationError(f"Invalid symbol: {symbol}")
        
        try:
            start_time = asyncio.get_event_loop().time()
            orderbook = await self.client.fetch_orderbook(symbol, depth)
            duration = asyncio.get_event_loop().time() - start_time
            
            perf_logger.execution_time("fetch_orderbook", duration)
            
            # Calculate spread and depth analysis
            best_bid = orderbook['bids'][0][0] if orderbook['bids'] else None
            best_ask = orderbook['asks'][0][0] if orderbook['asks'] else None
            
            spread = None
            spread_percent = None
            if best_bid and best_ask:
                spread = best_ask - best_bid
                mid_price = (best_bid + best_ask) / 2
                spread_percent = (spread / mid_price) * 100
            
            # Calculate total volume at each side
            bid_volume = sum(bid[1] for bid in orderbook['bids'])
            ask_volume = sum(ask[1] for ask in orderbook['asks'])
            
            return {
                'symbol': symbol,
                'timestamp': orderbook['timestamp'],
                'datetime': orderbook['datetime'],
                'bids': orderbook['bids'],
                'asks': orderbook['asks'],
                'best_bid': best_bid,
                'best_ask': best_ask,
                'spread': spread,
                'spread_percent': spread_percent,
                'bid_volume': bid_volume,
                'ask_volume': ask_volume,
                'volume_imbalance': (bid_volume - ask_volume) / (bid_volume + ask_volume) if (bid_volume + ask_volume) > 0 else 0,
            }
            
        except Exception as e:
            logger.error(f"Error fetching orderbook for {symbol}: {e}")
            raise MarketDataError(f"Failed to fetch orderbook for {symbol}: {e}")
    
    async def validate_symbol_trading(self, symbol: str) -> Dict[str, Any]:
        """Validate if a symbol meets trading criteria."""
        if not Validator.is_valid_symbol(symbol):
            return {
                'symbol': symbol,
                'valid': False,
                'reason': 'Invalid symbol format',
                'data': {}
            }
        
        try:
            # Get market summary and volume analysis
            market_summary = await self.get_market_summary(symbol)
            volume_analysis = await self.get_volume_analysis(symbol)
            
            # Validation criteria
            validations = {
                'has_price': market_summary['price'] is not None and market_summary['price'] > 0,
                'has_volume': market_summary['quote_volume_24h'] is not None and market_summary['quote_volume_24h'] >= TradingConfig.MIN_VOLUME_24H_USDT,
                'has_spread': market_summary['spread'] is not None,
                'reasonable_spread': market_summary['spread_percent'] is not None and market_summary['spread_percent'] < 1.0,  # Less than 1% spread
            }
            
            is_valid = all(validations.values())
            
            # Determine reason if invalid
            reason = None
            if not is_valid:
                failed_checks = [check for check, passed in validations.items() if not passed]
                reason = f"Failed validation checks: {', '.join(failed_checks)}"
            
            return {
                'symbol': symbol,
                'valid': is_valid,
                'reason': reason,
                'data': {
                    'market_summary': market_summary,
                    'volume_analysis': volume_analysis,
                    'validations': validations,
                }
            }
            
        except Exception as e:
            logger.error(f"Error validating symbol {symbol}: {e}")
            return {
                'symbol': symbol,
                'valid': False,
                'reason': f"Validation error: {str(e)}",
                'data': {}
            }
    
    async def get_market_status(self) -> Dict[str, Any]:
        """Get overall market status and statistics."""
        try:
            markets = await self.get_usdt_markets()
            
            # Get sample of major pairs for market overview
            major_pairs = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT']
            available_pairs = [pair for pair in major_pairs if any(m['symbol'] == pair for m in markets)]
            
            if available_pairs:
                tickers = await self.get_multiple_tickers(available_pairs[:3])  # Limit to avoid rate limits
            else:
                tickers = {}
            
            return {
                'total_markets': len(markets),
                'active_markets': len([m for m in markets if m['active']]),
                'major_pairs_status': tickers,
                'timestamp': datetime.utcnow().isoformat(),
                'client_initialized': self.client._initialized,
            }
            
        except Exception as e:
            logger.error(f"Error getting market status: {e}")
            return {
                'total_markets': 0,
                'active_markets': 0,
                'major_pairs_status': {},
                'timestamp': datetime.utcnow().isoformat(),
                'client_initialized': False,
                'error': str(e),
            }


# Global market data API instance
_market_data_api = None


def get_market_data_api() -> MarketDataAPI:
    """Get the global MarketDataAPI instance."""
    global _market_data_api
    if _market_data_api is None:
        _market_data_api = MarketDataAPI()
    return _market_data_api