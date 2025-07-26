# api/client.py
"""BingX exchange client using CCXT library."""

import asyncio
import ccxt
import logging
import time
from collections import defaultdict, deque
from typing import Dict, List, Optional, Any, Callable
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone

from config.settings import Settings
from utils.logger import get_logger
from utils.validators import Validator, ValidationError

logger = get_logger(__name__)


class BingXError(Exception):
    """Base exception for BingX API errors."""
    pass


class TradingAPIError(BingXError):
    """Exception for trading API errors."""
    pass


class MarketDataError(BingXError):
    """Exception for market data API errors."""
    pass


class RateLimitError(BingXError):
    """Exception for rate limit errors."""
    pass


class BingXClient:
    """Main BingX exchange client using CCXT."""
    
    def __init__(self):
        self.exchange = None
        self._initialized = False
        # Circuit breaker for rate limit protection
        self._circuit_breaker = {
            'is_open': False,
            'failure_count': 0,
            'failure_threshold': 3,
            'recovery_time': 300,  # 5 minutes
            'last_failure_time': 0
        }
        # BingX strict rate limits - ULTRA CONSERVATIVE with intelligent batching
        # Market interfaces: 100 requests per 10 seconds per IP = 10 req/s theoretical max
        # Account interfaces: 1,000 requests per 10 seconds per IP
        # Using extremely conservative limits with intelligent request management
        self._rate_limits = {
            # Market data endpoints - Optimized for better performance
            'fetch_ticker': 5.0,     # 5 per second (50% of BingX limit)
            'fetch_ohlcv': 5.0,      # 5 per second (50% of BingX limit)
            'fetch_markets': 2.0,    # 2 per second (minimal usage)
            'fetch_orderbook': 3.0,  # 3 per second (balanced)
            
            # Account endpoints - very conservative
            'create_order': 15,      # 15 per second (conservative for trading)
            'cancel_order': 15,      # 15 per second (conservative for trading)
            'fetch_balance': 1,      # 1 per second (ultra conservative)
            'fetch_order_status': 5, # 5 per second (conservative)
            'fetch_open_orders': 1,  # 1 per second (ultra conservative)
        }
        # Track requests per endpoint for rate limiting
        self._request_timestamps = defaultdict(deque)
        self._rate_limit_window = 10  # 10 seconds window
        
        # Request deduplication and caching
        self._pending_requests = {}  # Track pending identical requests
        self._request_cache = {}     # Cache recent results
        self._cache_ttl = {
            'fetch_ticker': 3,       # 3 seconds cache for tickers
            'fetch_ohlcv': 30,       # 30 seconds cache for OHLCV
            'fetch_markets': 300,    # 5 minutes cache for markets
            'fetch_orderbook': 5,    # 5 seconds cache for orderbook
        }
        
        # Request batching
        self._batch_queue = defaultdict(list)
        self._batch_timers = {}
        self._batch_size = 5
        self._batch_delay = 0.5  # 500ms batch window
        
        # Task cleanup
        self._last_cleanup = time.time()
        self._cleanup_interval = 60  # Cleanup every minute
        
    async def initialize(self) -> bool:
        """Initialize the CCXT exchange client."""
        try:
            # Validate required settings
            if not Settings.BINGX_API_KEY or not Settings.BINGX_SECRET_KEY:
                raise ValueError("BingX API credentials are required")
            
            # Initialize CCXT exchange
            self.exchange = ccxt.bingx({
                'apiKey': Settings.BINGX_API_KEY,
                'secret': Settings.BINGX_SECRET_KEY,
                'enableRateLimit': True,
                'rateLimit': 2000,  # 2000ms between requests (0.5 req/s ultra conservative)
                'timeout': Settings.REQUEST_TIMEOUT * 1000,  # Convert to ms
                'options': {
                    'defaultType': 'swap',  # Perpetual futures trading
                    'adjustForTimeDifference': True,
                },
                'sandbox': Settings.BINGX_TESTNET or Settings.BINGX_SANDBOX,
            })
            
            # Test connection
            await self._test_connection()
            
            self._initialized = True
            logger.info(f"BingX client initialized successfully (Testnet: {Settings.BINGX_TESTNET})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize BingX client: {e}")
            return False
    
    async def _test_connection(self):
        """Test API connection and credentials."""
        try:
            # Test public endpoint
            markets = await self._execute_with_retry(self.exchange.fetch_markets)
            if not markets:
                raise BingXError("No markets available")
            
            logger.info(f"BingX API connection test successful - found {len(markets)} markets")
            
            # Test private endpoint (if not sandbox)
            if not (Settings.BINGX_TESTNET or Settings.BINGX_SANDBOX):
                try:
                    balance = await self._execute_with_retry(self.exchange.fetch_balance)
                    if balance is not None:
                        logger.info("Private API access confirmed")
                except Exception as e:
                    logger.warning(f"Private API test failed (continuing anyway): {e}")
            
        except ccxt.AuthenticationError as e:
            raise BingXError(f"Authentication failed: {e}")
        except ccxt.NetworkError as e:
            raise BingXError(f"Network error: {e}")
        except ccxt.InvalidNonce as e:
            raise BingXError(f"Invalid nonce error (check system time): {e}")
        except Exception as e:
            raise BingXError(f"Connection test failed: {e}")
    
    def _check_initialized(self):
        """Check if client is initialized."""
        if not self._initialized:
            raise BingXError("Client not initialized. Call initialize() first.")
    
    async def _check_rate_limit(self, endpoint: str):
        """Check and enforce rate limits for specific endpoint."""
        current_time = time.time()
        timestamps = self._request_timestamps[endpoint]
        
        # Remove timestamps older than the window
        while timestamps and current_time - timestamps[0] > self._rate_limit_window:
            timestamps.popleft()
        
        # Get rate limit for this endpoint
        limit = self._rate_limits.get(endpoint, 5)  # Default to 5 req/s if not specified
        
        # Check if we're within the limit
        if len(timestamps) >= limit * self._rate_limit_window / 10:  # Convert to 10s window
            # Calculate how long to wait
            oldest_timestamp = timestamps[0]
            wait_time = self._rate_limit_window - (current_time - oldest_timestamp) + 0.1
            
            if wait_time > 0:
                logger.warning(f"Rate limit approaching for {endpoint}, waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                # Clean up timestamps again after waiting
                current_time = time.time()
                while timestamps and current_time - timestamps[0] > self._rate_limit_window:
                    timestamps.popleft()
        
        # Record this request
        timestamps.append(current_time)
    
    def _get_cache_key(self, func_name: str, *args, **kwargs) -> str:
        """Generate cache key for request."""
        # Create a hash of function name and arguments
        import hashlib
        key_parts = [func_name] + [str(arg) for arg in args] + [f"{k}={v}" for k, v in sorted(kwargs.items())]
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _get_cached_result(self, cache_key: str, endpoint: str) -> Optional[Any]:
        """Get cached result if valid."""
        if cache_key not in self._request_cache:
            return None
        
        cached_data = self._request_cache[cache_key]
        current_time = time.time()
        ttl = self._cache_ttl.get(endpoint, 60)
        
        if current_time - cached_data['timestamp'] > ttl:
            # Cache expired
            del self._request_cache[cache_key]
            return None
        
        logger.debug(f"Cache HIT for {endpoint}: {cache_key[:8]}")
        return cached_data['result']
    
    def _cache_result(self, cache_key: str, result: Any) -> None:
        """Cache result with timestamp."""
        self._request_cache[cache_key] = {
            'result': result,
            'timestamp': time.time()
        }
        
        # Periodic cleanup to prevent memory issues
        self._cleanup_caches()
    
    def _cleanup_caches(self) -> None:
        """Clean up stale caches and completed tasks."""
        current_time = time.time()
        
        # Only cleanup periodically to avoid overhead
        if current_time - self._last_cleanup < self._cleanup_interval:
            return
        
        self._last_cleanup = current_time
        
        # Clean up expired cache entries
        expired_keys = []
        for key, data in self._request_cache.items():
            if current_time - data['timestamp'] > 600:  # Remove entries older than 10 minutes
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._request_cache[key]
        
        # Clean up completed/cancelled tasks
        completed_tasks = []
        for key, task in self._pending_requests.items():
            if hasattr(task, 'done') and task.done():
                completed_tasks.append(key)
        
        for key in completed_tasks:
            del self._pending_requests[key]
        
        # Limit cache size
        if len(self._request_cache) > 1000:
            # Remove oldest entries
            oldest_keys = sorted(
                self._request_cache.items(),
                key=lambda x: x[1]['timestamp']
            )[:200]  # Remove more entries when cleanup runs
            for key, _ in oldest_keys:
                del self._request_cache[key]
        
        if expired_keys or completed_tasks:
            logger.debug(f"Cache cleanup: removed {len(expired_keys)} expired entries, {len(completed_tasks)} completed tasks")
    
    async def _deduplicated_request(self, func: Callable, endpoint: str, *args, **kwargs) -> Any:
        """Execute request with deduplication, caching, and rate limiting."""
        cache_key = self._get_cache_key(func.__name__, *args, **kwargs)
        
        # Check cache first
        cached_result = self._get_cached_result(cache_key, endpoint)
        if cached_result is not None:
            return cached_result
        
        # Check if same request is already pending
        if cache_key in self._pending_requests:
            logger.debug(f"Deduplicating request {endpoint}: {cache_key[:8]}")
            try:
                return await self._pending_requests[cache_key]
            except Exception as e:
                # If awaiting the pending request fails, remove it and retry
                logger.warning(f"Pending request failed, removing from cache: {e}")
                self._pending_requests.pop(cache_key, None)
                # Fall through to create new request
        
        # Create new request task (not coroutine) to avoid reuse issues
        async def make_request():
            try:
                # Apply rate limiting before actual request
                await self._check_rate_limit(endpoint)
                result = await self._execute_with_retry(func, *args, **kwargs)
                self._cache_result(cache_key, result)
                return result
            except Exception as e:
                logger.error(f"Request failed for {endpoint}: {e}")
                raise
            finally:
                # Remove from pending requests
                self._pending_requests.pop(cache_key, None)
        
        # Create and store the task (not coroutine)
        import asyncio
        task = asyncio.create_task(make_request())
        self._pending_requests[cache_key] = task
        
        try:
            return await task
        except Exception as e:
            # Clean up on error
            self._pending_requests.pop(cache_key, None)
            raise
    
    def _check_circuit_breaker(self):
        """Check if circuit breaker should allow requests."""
        current_time = time.time()
        cb = self._circuit_breaker
        
        # If circuit is open, check if we can try to recover
        if cb['is_open']:
            if current_time - cb['last_failure_time'] > cb['recovery_time']:
                logger.info("Circuit breaker attempting recovery...")
                cb['is_open'] = False
                cb['failure_count'] = 0
            else:
                remaining = cb['recovery_time'] - (current_time - cb['last_failure_time'])
                raise RateLimitError(f"Circuit breaker open - retry in {remaining:.0f}s")
    
    def _record_success(self):
        """Record successful request."""
        if self._circuit_breaker['failure_count'] > 0:
            self._circuit_breaker['failure_count'] = max(0, self._circuit_breaker['failure_count'] - 1)
    
    def _record_failure(self):
        """Record failed request."""
        cb = self._circuit_breaker
        cb['failure_count'] += 1
        cb['last_failure_time'] = time.time()
        
        if cb['failure_count'] >= cb['failure_threshold']:
            cb['is_open'] = True
            logger.warning(f"Circuit breaker opened after {cb['failure_count']} failures")

    async def _execute_with_retry(self, func: Callable, *args, max_retries: int = 5, 
                                 delay_factor: float = 2.0) -> Any:
        """Execute function with retry logic, exponential backoff, and circuit breaker."""
        # Check circuit breaker first
        self._check_circuit_breaker()
        
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                # Check if function is coroutine (async) or regular function
                result = func(*args)
                if asyncio.iscoroutine(result):
                    result = await result
                
                # Record success and return
                self._record_success()
                return result
            except ccxt.RateLimitExceeded as e:
                self._record_failure()  # Record failure for circuit breaker
                logger.warning(f"Rate limit hit on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    raise RateLimitError(f"Rate limit exceeded after {max_retries} attempts")
                # Aggressive exponential backoff for rate limits
                backoff_delay = delay_factor * (3 ** attempt) + (attempt * 5)  # Even more aggressive
                logger.info(f"Rate limit backoff: waiting {backoff_delay:.1f}s before retry {attempt + 2}")
                await asyncio.sleep(backoff_delay)
                last_exception = e
            except ccxt.NetworkError as e:
                logger.warning(f"Network error on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    raise BingXError(f"Network error after {max_retries} attempts: {e}")
                await asyncio.sleep(delay_factor * (2 ** attempt))
                last_exception = e
            except ccxt.ExchangeError as e:
                # Don't retry exchange errors - they're usually permanent
                logger.error(f"Exchange error: {e}")
                raise BingXError(f"Exchange error: {e}")
            except Exception as e:
                logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    raise BingXError(f"Unexpected error after {max_retries} attempts: {e}")
                await asyncio.sleep(delay_factor * (2 ** attempt))
                last_exception = e
        
        raise last_exception
    
    # Market Data Methods
    
    async def fetch_markets(self) -> List[Dict[str, Any]]:
        """Fetch all available USDT spot markets."""
        self._check_initialized()
        await self._check_rate_limit('fetch_markets')
        
        try:
            markets = await self._execute_with_retry(self.exchange.fetch_markets)
            
            # Filter for USDT pairs and convert to standard format
            usdt_markets = []
            for market in markets:
                # Look for USDT pairs
                symbol = market.get('symbol', '')
                base_currency = market.get('base', '')
                quote_currency = market.get('quote', '')
                
                # Filter for USDT markets only
                if quote_currency == 'USDT' and market.get('active', False):
                    # Ensure symbol is in BTC/USDT format
                    formatted_symbol = f"{base_currency}/USDT"
                    
                    usdt_markets.append({
                        'symbol': formatted_symbol,
                        'base': base_currency,
                        'quote': 'USDT',
                        'active': market.get('active', False),
                        'limits': market.get('limits', {
                            'amount': {'min': 0, 'max': 0},
                            'cost': {'min': 0, 'max': 0}
                        }),
                        'precision': market.get('precision', {
                            'price': 8,
                            'amount': 6
                        }),
                        'maker_fee': market.get('maker', 0.001),
                        'taker_fee': market.get('taker', 0.001),
                        'raw_data': market  # Keep original data for reference
                    })
            
            logger.info(f"Fetched {len(usdt_markets)} USDT markets")
            return usdt_markets
            
        except Exception as e:
            logger.error(f"Error fetching markets: {e}")
            raise MarketDataError(f"Failed to fetch markets: {e}")
    
    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch current market ticker data with caching and deduplication."""
        self._check_initialized()
        
        if not Validator.is_valid_symbol(symbol):
            raise ValidationError(f"Invalid symbol format: {symbol}")
        
        try:
            # Use deduplicated request with caching
            ticker = await self._deduplicated_request(
                self.exchange.fetch_ticker, 'fetch_ticker', symbol
            )
            
            # Safe access to ticker data with proper error handling
            def safe_decimal(value):
                """Safely convert value to Decimal"""
                try:
                    return Decimal(str(value)) if value is not None else None
                except (TypeError, ValueError, InvalidOperation):
                    return None

            return {
                'symbol': symbol,
                'timestamp': ticker.get('timestamp'),
                'datetime': ticker.get('datetime'),
                'last': safe_decimal(ticker.get('last')),
                'bid': safe_decimal(ticker.get('bid')),
                'ask': safe_decimal(ticker.get('ask')),
                'volume': safe_decimal(ticker.get('baseVolume')),
                'quote_volume': safe_decimal(ticker.get('quoteVolume')),
                'quoteVolume': safe_decimal(ticker.get('quoteVolume')),  # Alternative key for compatibility
                'change': safe_decimal(ticker.get('change')),
                'percentage': safe_decimal(ticker.get('percentage')),
                'high': safe_decimal(ticker.get('high')),
                'low': safe_decimal(ticker.get('low')),
                'open': safe_decimal(ticker.get('open')),
                'raw_ticker': ticker  # Keep raw data for debugging
            }
            
        except Exception as e:
            logger.error(f"Error fetching ticker for {symbol}: {e}")
            raise MarketDataError(f"Failed to fetch ticker for {symbol}: {e}")
    
    async def fetch_ohlcv(self, symbol: str, timeframe: str = '1h', 
                         limit: int = 100, since: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch OHLCV candlestick data with caching and deduplication."""
        self._check_initialized()
        
        if not Validator.is_valid_symbol(symbol):
            raise ValidationError(f"Invalid symbol format: {symbol}")
        
        if not Validator.is_valid_timeframe(timeframe):
            raise ValidationError(f"Invalid timeframe: {timeframe}")
        
        try:
            # Convert BTC/VST format to BTC-VST for BingX API
            bingx_symbol = symbol.replace('/', '-')
            candles = await self._deduplicated_request(
                self.exchange.fetch_ohlcv, 'fetch_ohlcv', 
                bingx_symbol, timeframe, since, limit
            )
            
            formatted_candles = []
            for candle in candles:
                formatted_candles.append({
                    'timestamp': candle[0],
                    'datetime': datetime.fromtimestamp(candle[0] / 1000, tz=timezone.utc).isoformat(),
                    'open': Decimal(str(candle[1])),
                    'high': Decimal(str(candle[2])),
                    'low': Decimal(str(candle[3])),
                    'close': Decimal(str(candle[4])),
                    'volume': Decimal(str(candle[5])),
                })
            
            logger.debug(f"Fetched {len(formatted_candles)} candles for {symbol} {timeframe}")
            return formatted_candles
            
        except Exception as e:
            logger.error(f"Error fetching OHLCV for {symbol} {timeframe}: {e}")
            raise MarketDataError(f"Failed to fetch OHLCV for {symbol} {timeframe}: {e}")
    
    async def fetch_orderbook(self, symbol: str, limit: int = 20) -> Dict[str, Any]:
        """Fetch order book data."""
        self._check_initialized()
        await self._check_rate_limit('fetch_orderbook')
        
        if not Validator.is_valid_symbol(symbol):
            raise ValidationError(f"Invalid symbol format: {symbol}")
        
        try:
            # Convert BTC/VST format to BTC-VST for BingX API
            bingx_symbol = symbol.replace('/', '-')
            orderbook = await self._execute_with_retry(
                self.exchange.fetch_order_book, bingx_symbol, limit
            )
            
            return {
                'symbol': symbol,
                'timestamp': orderbook.get('timestamp'),
                'datetime': orderbook.get('datetime'),
                'bids': [[Decimal(str(bid[0])), Decimal(str(bid[1]))] for bid in orderbook['bids']],
                'asks': [[Decimal(str(ask[0])), Decimal(str(ask[1]))] for ask in orderbook['asks']],
            }
            
        except Exception as e:
            logger.error(f"Error fetching orderbook for {symbol}: {e}")
            raise MarketDataError(f"Failed to fetch orderbook for {symbol}: {e}")
    
    # Trading Methods
    
    async def fetch_balance(self) -> Dict[str, Dict[str, Decimal]]:
        """Fetch account balance."""
        self._check_initialized()
        await self._check_rate_limit('fetch_balance')
        
        try:
            balance = await self._execute_with_retry(self.exchange.fetch_balance)
            
            formatted_balance = {}
            for currency, data in balance.items():
                if currency not in ['info', 'free', 'used', 'total'] and isinstance(data, dict):
                    formatted_balance[currency] = {
                        'free': Decimal(str(data.get('free', 0))),
                        'used': Decimal(str(data.get('used', 0))),
                        'total': Decimal(str(data.get('total', 0))),
                    }
            
            logger.debug(f"Fetched balance for {len(formatted_balance)} currencies")
            return formatted_balance
            
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            raise TradingAPIError(f"Failed to fetch balance: {e}")
    
    async def create_market_order(self, symbol: str, side: str, amount: Decimal, 
                                 params: Optional[Dict] = None) -> Dict[str, Any]:
        """Create a market order."""
        self._check_initialized()
        await self._check_rate_limit('create_order')
        
        if not Validator.is_valid_symbol(symbol):
            raise ValidationError(f"Invalid symbol format: {symbol}")
        
        if not Validator.is_valid_side(side):
            raise ValidationError(f"Invalid side: {side}")
        
        if not Validator.is_valid_quantity(amount):
            raise ValidationError(f"Invalid amount: {amount}")
        
        try:
            # Convert BTC/VST format to BTC-VST for BingX API
            bingx_symbol = symbol.replace('/', '-')
            order = await self._execute_with_retry(
                self.exchange.create_market_order, 
                bingx_symbol, side.lower(), float(amount), None, None, params or {}
            )
            
            return {
                'id': order['id'],
                'timestamp': order.get('timestamp'),
                'datetime': order.get('datetime'),
                'symbol': order['symbol'],
                'type': order['type'],
                'side': order['side'],
                'amount': Decimal(str(order['amount'])),
                'price': Decimal(str(order.get('price', 0))) if order.get('price') else None,
                'average': Decimal(str(order.get('average', 0))) if order.get('average') else None,
                'filled': Decimal(str(order.get('filled', 0))),
                'remaining': Decimal(str(order.get('remaining', 0))),
                'cost': Decimal(str(order.get('cost', 0))) if order.get('cost') else None,
                'status': order['status'],
                'fee': order.get('fee'),
                'trades': order.get('trades', []),
                'info': order.get('info', {}),
            }
            
        except Exception as e:
            logger.error(f"Error creating market order for {symbol}: {e}")
            raise TradingAPIError(f"Failed to create market order: {e}")
    
    async def create_limit_order(self, symbol: str, side: str, amount: Decimal, 
                                price: Decimal, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Create a limit order."""
        self._check_initialized()
        await self._check_rate_limit('create_order')
        
        if not Validator.is_valid_symbol(symbol):
            raise ValidationError(f"Invalid symbol format: {symbol}")
        
        if not Validator.is_valid_side(side):
            raise ValidationError(f"Invalid side: {side}")
        
        if not Validator.is_valid_quantity(amount):
            raise ValidationError(f"Invalid amount: {amount}")
        
        if not Validator.is_valid_price(price):
            raise ValidationError(f"Invalid price: {price}")
        
        try:
            # Convert BTC/VST format to BTC-VST for BingX API
            bingx_symbol = symbol.replace('/', '-')
            order = await self._execute_with_retry(
                self.exchange.create_limit_order,
                bingx_symbol, side.lower(), float(amount), float(price), params or {}
            )
            
            return {
                'id': order['id'],
                'timestamp': order.get('timestamp'),
                'datetime': order.get('datetime'),
                'symbol': order['symbol'],
                'type': order['type'],
                'side': order['side'],
                'amount': Decimal(str(order['amount'])),
                'price': Decimal(str(order['price'])),
                'average': Decimal(str(order.get('average', 0))) if order.get('average') else None,
                'filled': Decimal(str(order.get('filled', 0))),
                'remaining': Decimal(str(order.get('remaining', 0))),
                'cost': Decimal(str(order.get('cost', 0))) if order.get('cost') else None,
                'status': order['status'],
                'fee': order.get('fee'),
                'trades': order.get('trades', []),
                'info': order.get('info', {}),
            }
            
        except Exception as e:
            logger.error(f"Error creating limit order for {symbol}: {e}")
            raise TradingAPIError(f"Failed to create limit order: {e}")
    
    async def create_stop_loss_order(self, symbol: str, side: str, amount: Decimal,
                                    stop_price: Decimal, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Create a stop loss order."""
        self._check_initialized()
        await self._check_rate_limit('create_order')
        
        if not Validator.is_valid_symbol(symbol):
            raise ValidationError(f"Invalid symbol format: {symbol}")
        
        if not Validator.is_valid_side(side):
            raise ValidationError(f"Invalid side: {side}")
        
        if not Validator.is_valid_quantity(amount):
            raise ValidationError(f"Invalid amount: {amount}")
        
        if not Validator.is_valid_price(stop_price):
            raise ValidationError(f"Invalid stop price: {stop_price}")
        
        try:
            order_params = {
                'stopPrice': float(stop_price),
                **(params or {})
            }
            
            # Convert BTC/VST format to BTC-VST for BingX API
            bingx_symbol = symbol.replace('/', '-')
            order = await self._execute_with_retry(
                self.exchange.create_order,
                bingx_symbol, 'stop_market', side.lower(), float(amount), None, order_params
            )
            
            return {
                'id': order['id'],
                'timestamp': order.get('timestamp'),
                'datetime': order.get('datetime'),
                'symbol': order['symbol'],
                'type': order['type'],
                'side': order['side'],
                'amount': Decimal(str(order['amount'])),
                'price': Decimal(str(order.get('price', 0))) if order.get('price') else None,
                'stop_price': stop_price,
                'status': order['status'],
                'info': order.get('info', {}),
            }
            
        except Exception as e:
            logger.error(f"Error creating stop loss order for {symbol}: {e}")
            raise TradingAPIError(f"Failed to create stop loss order: {e}")
    
    async def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Cancel an existing order."""
        self._check_initialized()
        await self._check_rate_limit('cancel_order')
        
        if not Validator.is_valid_symbol(symbol):
            raise ValidationError(f"Invalid symbol format: {symbol}")
        
        try:
            # Convert BTC/VST format to BTC-VST for BingX API
            bingx_symbol = symbol.replace('/', '-')
            result = await self._execute_with_retry(
                self.exchange.cancel_order, order_id, bingx_symbol
            )
            
            logger.info(f"Order {order_id} cancelled successfully")
            return result
            
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            raise TradingAPIError(f"Failed to cancel order {order_id}: {e}")
    
    async def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Fetch order details."""
        self._check_initialized()
        await self._check_rate_limit('fetch_order_status')
        
        if not Validator.is_valid_symbol(symbol):
            raise ValidationError(f"Invalid symbol format: {symbol}")
        
        try:
            # Convert BTC/VST format to BTC-VST for BingX API
            bingx_symbol = symbol.replace('/', '-')
            order = await self._execute_with_retry(
                self.exchange.fetch_order, order_id, bingx_symbol
            )
            
            return {
                'id': order['id'],
                'timestamp': order.get('timestamp'),
                'datetime': order.get('datetime'),
                'symbol': order['symbol'],
                'type': order['type'],
                'side': order['side'],
                'amount': Decimal(str(order['amount'])),
                'price': Decimal(str(order.get('price', 0))) if order.get('price') else None,
                'average': Decimal(str(order.get('average', 0))) if order.get('average') else None,
                'filled': Decimal(str(order.get('filled', 0))),
                'remaining': Decimal(str(order.get('remaining', 0))),
                'cost': Decimal(str(order.get('cost', 0))) if order.get('cost') else None,
                'status': order['status'],
                'fee': order.get('fee'),
                'trades': order.get('trades', []),
                'info': order.get('info', {}),
            }
            
        except Exception as e:
            logger.error(f"Error fetching order {order_id}: {e}")
            raise TradingAPIError(f"Failed to fetch order {order_id}: {e}")
    
    async def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch open orders."""
        self._check_initialized()
        await self._check_rate_limit('fetch_open_orders')
        
        if symbol and not Validator.is_valid_symbol(symbol):
            raise ValidationError(f"Invalid symbol format: {symbol}")
        
        try:
            # Convert BTC/USDT format to BTC-USDT for BingX API if symbol provided
            bingx_symbol = symbol.replace('/', '-') if symbol else None
            orders = await self._execute_with_retry(
                self.exchange.fetch_open_orders, bingx_symbol
            )
            
            formatted_orders = []
            for order in orders:
                formatted_orders.append({
                    'id': order['id'],
                    'timestamp': order.get('timestamp'),
                    'datetime': order.get('datetime'),
                    'symbol': order['symbol'],
                    'type': order['type'],
                    'side': order['side'],
                    'amount': Decimal(str(order['amount'])),
                    'price': Decimal(str(order.get('price', 0))) if order.get('price') else None,
                    'filled': Decimal(str(order.get('filled', 0))),
                    'remaining': Decimal(str(order.get('remaining', 0))),
                    'status': order['status'],
                })
            
            logger.debug(f"Fetched {len(formatted_orders)} open orders")
            return formatted_orders
            
        except Exception as e:
            logger.error(f"Error fetching open orders: {e}")
            raise TradingAPIError(f"Failed to fetch open orders: {e}")
    
    async def close(self):
        """Close the exchange client and cleanup resources."""
        if self.exchange:
            try:
                # CCXT exchange objects don't have a close method
                # Just clear the reference
                self.exchange = None
                logger.info("BingX client closed successfully")
            except Exception as e:
                logger.error(f"Error closing BingX client: {e}")
        
        self._initialized = False
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._initialized:
            asyncio.create_task(self.close())


# Global client instance
_bingx_client = None


def get_client() -> BingXClient:
    """Get the global BingX client instance."""
    global _bingx_client
    if _bingx_client is None:
        _bingx_client = BingXClient()
    return _bingx_client


async def initialize_client() -> bool:
    """Initialize the global BingX client."""
    client = get_client()
    return await client.initialize()


async def close_client():
    """Close the global BingX client."""
    global _bingx_client
    if _bingx_client:
        await _bingx_client.close()
        _bingx_client = None


def get_rate_limit_status() -> Dict[str, Any]:
    """Get current rate limit status for monitoring."""
    client = get_client()
    if not client._initialized:
        return {"status": "not_initialized"}
    
    current_time = time.time()
    status = {
        "status": "active",
        "circuit_breaker": client._circuit_breaker.copy(),
        "cache_stats": {
            "cache_size": len(client._request_cache),
            "pending_requests": len(client._pending_requests),
        },
        "rate_limits": {}
    }
    
    # Calculate rate limit utilization for each endpoint
    for endpoint, limit in client._rate_limits.items():
        timestamps = client._request_timestamps[endpoint]
        # Count requests in the current window
        recent_requests = sum(1 for ts in timestamps if current_time - ts <= client._rate_limit_window)
        max_requests = limit * client._rate_limit_window / 10  # Convert to 10s window
        
        status["rate_limits"][endpoint] = {
            "requests_in_window": recent_requests,
            "max_requests": int(max_requests),
            "utilization_percent": round((recent_requests / max_requests * 100) if max_requests > 0 else 0, 2)
        }
    
    return status


def clear_api_cache():
    """Clear API request cache for testing or reset."""
    client = get_client()
    
    # Cancel all pending tasks first
    import asyncio
    for key, task in list(client._pending_requests.items()):
        if hasattr(task, 'cancel'):
            task.cancel()
    
    client._request_cache.clear()
    client._pending_requests.clear()
    logger.info("API cache and pending requests cleared")


def force_cleanup_tasks():
    """Force cleanup of completed and stale tasks."""
    client = get_client()
    if hasattr(client, '_cleanup_caches'):
        client._last_cleanup = 0  # Force cleanup
        client._cleanup_caches()
        logger.info("Forced task cleanup completed")