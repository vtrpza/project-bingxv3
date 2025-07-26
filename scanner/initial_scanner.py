# scanner/initial_scanner.py
"""Initial asset scanner for discovering and validating trading assets."""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone

from api.market_data import get_market_data_api, MarketDataError
from api.client import get_client
from database.connection import get_session
from database.repository import AssetRepository
from database.models import Asset
from config.trading_config import TradingConfig
from utils.logger import get_logger, trading_logger
from utils.datetime_utils import utc_now, safe_datetime_subtract
from utils.rate_limiter import get_rate_limiter
from utils.smart_cache import get_smart_cache
from utils.converters import convert_decimals
from api.web_api import manager as connection_manager
from scanner.symbol_cache import get_symbol_cache, SymbolData

# Imports for progress reporting
from scanner.scanner_config import get_scanner_config, ScannerConfig
from scanner.progress_observers import (
    ProgressReporter, CompositeProgressObserver, WebSocketProgressObserver, 
    LoggingProgressObserver, ProgressEvent
)

logger = get_logger(__name__)


class InitialScanResult:
    """Container for initial scan results."""
    
    def __init__(self):
        self.total_discovered = 0
        self.valid_assets = []
        self.invalid_assets = []
        self.errors = []
        self.scan_duration = 0.0
        self.scan_timestamp = None
    
    def add_valid_asset(self, symbol: str, validation_data: Dict[str, Any]):
        """Add a valid asset to results."""
        self.valid_assets.append({
            'symbol': symbol,
            'validation_data': validation_data,
            'added_timestamp': utc_now().isoformat()
        })
    
    def add_invalid_asset(self, symbol: str, reason: str, validation_data: Dict[str, Any] = None):
        """Add an invalid asset to results."""
        self.invalid_assets.append({
            'symbol': symbol,
            'reason': reason,
            'validation_data': validation_data or {},
            'rejected_timestamp': utc_now().isoformat()
        })
    
    def add_error(self, symbol: str, error: str):
        """Add an error encountered during scanning."""
        self.errors.append({
            'symbol': symbol,
            'error': error,
            'timestamp': utc_now().isoformat()
        })
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of scan results."""
        return {
            'scan_timestamp': self.scan_timestamp,
            'scan_duration_seconds': self.scan_duration,
            'total_discovered': self.total_discovered,
            'valid_assets_count': len(self.valid_assets),
            'invalid_assets_count': len(self.invalid_assets),
            'errors_count': len(self.errors),
            'success_rate': (len(self.valid_assets) / self.total_discovered * 100) if self.total_discovered > 0 else 0,
            'valid_assets': [asset['symbol'] for asset in self.valid_assets],
            'top_invalid_reasons': self._get_top_invalid_reasons(),
        }
    
    def _get_top_invalid_reasons(self) -> List[Tuple[str, int]]:
        """Get most common reasons for asset rejection."""
        reason_counts = {}
        for asset in self.invalid_assets:
            reason = asset['reason']
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        
        return sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:5]


class InitialScanner:
    """Performs initial discovery of all available trading assets and populates database.
    
    Simplified implementation focusing on:
    - Fast discovery of all market symbols
    - Basic market data collection
    - Database population with discovered assets
    - Progress reporting via WebSocket
    - Leaves validation to the trading scanner
    """
    
    def __init__(self, config: Optional[ScannerConfig] = None, 
                 progress_reporter: Optional[ProgressReporter] = None):
        # Core dependencies for market discovery
        self.market_api = get_market_data_api()
        self.asset_repo = AssetRepository()
        self.client = get_client()
        self.rate_limiter = get_rate_limiter()
        self.cache = get_smart_cache()
        self.symbol_cache = get_symbol_cache(ttl_seconds=600)  # 10 minutes TTL
        
        # Configuration
        self.config = config or get_scanner_config()
        
        # Setup progress reporting with multiple observers
        if progress_reporter is None:
            composite_observer = CompositeProgressObserver()
            composite_observer.add_observer(WebSocketProgressObserver(connection_manager))
            composite_observer.add_observer(LoggingProgressObserver(logger))
            self.progress_reporter = ProgressReporter(composite_observer)
        else:
            self.progress_reporter = progress_reporter
        
        # Performance tracking (simplified)
        self._scan_stats = {
            'total_processed': 0,
            'successful_discoveries': 0,
            'failed_discoveries': 0,
            'cache_hits': 0,
            'api_calls': 0,
            'errors': []
        }
        
    async def scan_all_assets(self, force_refresh: bool = False, 
                            max_assets: Optional[int] = None) -> InitialScanResult:
        """Perform complete initial scan of all available assets - simplified to only fetch and populate.
        
        Args:
            force_refresh: Force refresh of cached market data
            max_assets: Maximum number of assets to process (None for all)
            
        Returns:
            InitialScanResult containing scan results and statistics
        """
        scan_start = utc_now()
        result = InitialScanResult()
        result.scan_timestamp = scan_start.isoformat()
        
        try:
            await self.progress_reporter.report_started(
                "Iniciando descoberta e população de ativos...",
                metadata={
                    'force_refresh': force_refresh,
                    'max_assets': max_assets,
                    'mode': 'fetch_and_populate'
                }
            )
            
            # Simplified process: discover -> extract -> save basic data
            markets = await self._discover_markets_step(force_refresh)
            if not markets:
                await self.progress_reporter.report_error("Nenhum mercado descoberto")
                return result
            
            symbols = await self._extract_symbols_step(markets, max_assets)
            result.total_discovered = len(symbols)
            
            # Save basic market data (no validation)
            await self._save_basic_assets_step(symbols, markets)
            await self._process_basic_results_step(symbols, result)
            
            # Finalize scan
            scan_end = utc_now()
            result.scan_duration = (scan_end - scan_start).total_seconds()
            
            await self._finalize_scan(result, scan_start, scan_end)
            return result
            
        except Exception as e:
            logger.error(f"Critical error during initial scan: {e}")
            await self._handle_scan_error(e, result, scan_start)
            return result
        finally:
            # Cleanup and resource management
            await self._cleanup_resources()
    
    async def _discover_markets_step(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Step 1: Discover all available markets from the exchange."""
        await self.progress_reporter.report_step_progress(
            "Descobrindo mercados disponíveis...", 1, self.config.broadcast_progress_steps
        )
        
        # Check cache first if not forcing refresh
        if not force_refresh:
            cached_symbols = await self.symbol_cache.get_all_symbols()
            if cached_symbols:
                logger.info(f"Found {len(cached_symbols)} symbols in cache")
                # For now, still fetch fresh market data but this provides a quick count
        
        try:
            self._scan_stats['api_calls'] += 1
            markets = await self.market_api.get_usdt_markets(force_refresh)
            logger.info(f"Discovered {len(markets)} markets from exchange")
            return markets
        except Exception as e:
            logger.error(f"Failed to discover markets: {e}")
            self._scan_stats['errors'].append(f"Market discovery failed: {str(e)}")
            raise
    
    async def _extract_symbols_step(self, markets: List[Dict[str, Any]], max_assets: Optional[int] = None) -> List[str]:
        """Step 2: Extract and prioritize USDT trading pair symbols."""
        await self.progress_reporter.report_step_progress(
            "Filtrando e priorizando pares USDT...", 2, self.config.broadcast_progress_steps
        )
        
        symbols = self._extract_usdt_symbols(markets)
        
        # Apply max_assets limit if specified
        if max_assets and max_assets > 0:
            original_count = len(symbols)
            symbols = symbols[:max_assets]
            logger.info(f"Limited assets from {original_count} to {len(symbols)} based on max_assets parameter")
        else:
            logger.info(f"Processing ALL {len(symbols)} discovered assets")
        
        return symbols
    
    def _extract_usdt_symbols(self, markets: List[Dict[str, Any]]) -> List[str]:
        """Extract USDT trading pair symbols from market data with validation."""
        symbols = []
        invalid_markets = 0
        
        logger.info("Extracting all active USDT pairs...")
        
        for market in markets:
            try:
                symbol = market.get('symbol', '').strip()
                # We are interested in perpetual swap contracts ending in USDT
                if symbol.endswith('USDT') and market.get('active', False):
                    symbols.append(symbol)
            except Exception as e:
                invalid_markets += 1
                logger.warning(f"Error processing market data for symbol '{market.get('symbol', 'N/A')}': {e}")
                continue
        
        logger.info(f"Found {len(symbols)} active USDT pairs ({invalid_markets} invalid markets skipped)")
        self._scan_stats['api_calls'] += 1

        # Simple alphabetical sort for consistent processing
        return sorted(symbols)
    
    async def _save_basic_assets_step(self, symbols: List[str], markets: List[Dict[str, Any]]) -> None:
        """Step 3: Save basic asset data to database (no validation)."""
        await self.progress_reporter.report_step_progress(
            f"Salvando {len(symbols)} ativos no banco de dados...",
            3, self.config.broadcast_progress_steps
        )
        
        try:
            # Create a mapping of symbols to market data for faster lookup
            market_by_symbol = {market.get('symbol', ''): market for market in markets}
            
            # Process in batches for better memory usage
            batch_size = self.config.db_batch_size
            total_saved = 0
            
            for i in range(0, len(symbols), batch_size):
                batch_symbols = symbols[i:i + batch_size]
                await self._save_basic_assets_batch(batch_symbols, market_by_symbol)
                total_saved += len(batch_symbols)
                
                # Report progress for large datasets
                if len(symbols) > 100 and total_saved % self.config.progress_report_interval == 0:
                    await self.progress_reporter.report_item_progress(
                        f"Salvando ativos... {total_saved}/{len(symbols)}",
                        total_saved, len(symbols)
                    )
            
            self._scan_stats['total_processed'] = total_saved
            logger.info(f"Successfully saved {total_saved} basic assets to database")
            
        except Exception as e:
            logger.error(f"Critical error saving basic assets: {e}")
            self._scan_stats['errors'].append(f"Database save failed: {str(e)}")
            raise
    
    async def _save_basic_assets_batch(self, symbols: List[str], market_by_symbol: Dict[str, Dict[str, Any]]) -> None:
        """Save a batch of basic assets to database using merge for robust upserts."""
        if not symbols:
            return
            
        bulk_insert_data = []
        current_time = utc_now()
        
        for symbol in symbols:
            try:
                # Get market data for this symbol
                market_data = market_by_symbol.get(symbol, {})
                
                # Extract basic information
                if '/' in symbol:
                    base_currency, quote_currency = symbol.split('/', 1)
                else:
                    # Handle symbols like BTCUSDT
                    if symbol.endswith('USDT'):
                        base_currency = symbol[:-4]
                        quote_currency = 'USDT'
                    else:
                        logger.warning(f"Could not parse symbol: {symbol}")
                        continue
                
                # Get basic market info if available - ensure float conversion
                min_order_size = market_data.get('limits', {}).get('amount', {}).get('min', TradingConfig.MIN_ORDER_SIZE_USDT)
                if not isinstance(min_order_size, (int, float)):
                    min_order_size = float(TradingConfig.MIN_ORDER_SIZE_USDT)
                else:
                    min_order_size = float(min_order_size)  # Convert Decimal to float
                
                # Basic validation data - just mark as discovered, not validated
                # Clean market data from Decimal objects
                clean_market_data = self._clean_decimal_data(market_data)
                
                basic_data = {
                    'discovered_timestamp': current_time.isoformat(),
                    'market_info': {
                        'active': clean_market_data.get('active', True),
                        'type': clean_market_data.get('type', 'swap'),
                        'spot': clean_market_data.get('spot', False),
                        'margin': clean_market_data.get('margin', False),
                        'future': clean_market_data.get('future', False),
                        'option': clean_market_data.get('option', False),
                        'swap': clean_market_data.get('swap', True),
                        'contract': clean_market_data.get('contract', True)
                    },
                    'limits': clean_market_data.get('limits', {}),
                    'precision': clean_market_data.get('precision', {}),
                    'needs_validation': True,  # Flag to indicate this needs to be validated by trading scanner
                    'scan_source': 'initial_discovery'
                }
                
                bulk_insert_data.append({
                    'symbol': symbol,
                    'base_currency': base_currency,
                    'quote_currency': quote_currency,
                    'is_valid': None,  # Not validated yet
                    'min_order_size': min_order_size,
                    'last_validation': None,  # No validation performed
                    'validation_data': basic_data
                })
                
                # Cache the symbol data with clean market data
                symbol_data = SymbolData(
                    symbol=symbol,
                    is_valid=None,  # Not validated yet
                    market_data=clean_market_data,
                    validation_data=basic_data
                )
                await self.symbol_cache.set(symbol, symbol_data)
                
            except Exception as e:
                logger.warning(f"Error preparing basic data for {symbol}: {e}")
                continue
        
        # Save to database using merge for reliable upserts
        if not bulk_insert_data:
            logger.debug("No data to save to database")
            return
            
        try:
            with get_session() as session:
                insert_count = 0
                update_count = 0
                error_count = 0
                
                for insert_data in bulk_insert_data:
                    symbol = insert_data['symbol']
                    
                    try:
                        # Check if asset already exists
                        existing_asset = session.query(Asset).filter(Asset.symbol == symbol).first()
                        
                        if existing_asset:
                            # Update existing asset's fields
                            existing_asset.is_valid = insert_data.get('is_valid')
                            existing_asset.min_order_size = insert_data.get('min_order_size')
                            existing_asset.last_validation = insert_data.get('last_validation')
                            existing_asset.validation_data = insert_data.get('validation_data')
                            update_count += 1
                            logger.debug(f"Updated existing asset: {symbol}")
                        else:
                            # Create new asset
                            new_asset = Asset(
                                symbol=symbol,
                                base_currency=insert_data['base_currency'],
                                quote_currency=insert_data['quote_currency'],
                                is_valid=insert_data.get('is_valid'),
                                min_order_size=insert_data.get('min_order_size'),
                                last_validation=insert_data.get('last_validation'),
                                validation_data=insert_data.get('validation_data')
                            )
                            session.add(new_asset)
                            insert_count += 1
                            logger.debug(f"Created new asset: {symbol}")
                        
                        # Flush after each asset to catch constraint violations early
                        session.flush()
                                
                    except Exception as symbol_error:
                        # Rollback changes for this symbol and continue
                        session.rollback()
                        error_count += 1
                        logger.warning(f"Error processing symbol {symbol}: {symbol_error}")
                        # Start a fresh transaction
                        session.begin()
                        continue
                
                # Commit all successful operations
                session.commit()
                logger.info(f"Batch operation completed: {insert_count} new assets, {update_count} updated, {error_count} errors")
                
        except Exception as db_error:
            logger.error(f"Database batch operation failed: {db_error}")
            # Don't re-raise to allow the scan to continue
            logger.info("Continuing scan despite database errors...")
    
    async def _process_basic_results_step(self, symbols: List[str], result: InitialScanResult) -> None:
        """Step 4: Intelligent post-processing with real trading validation."""
        await self.progress_reporter.report_step_progress(
            "Validando símbolos para trading...", 4, self.config.broadcast_progress_steps
        )
        
        # Perform intelligent validation of discovered symbols
        await self._validate_symbols_for_trading(symbols, result)
    
    async def _validate_symbols_for_trading(self, symbols: List[str], result: InitialScanResult) -> None:
        """Intelligent validation of symbols based on trading criteria."""
        logger.info(f"🔍 Starting intelligent validation of {len(symbols)} symbols...")
        
        # Trading validation criteria
        MIN_VOLUME_24H = 500000  # $500k minimum daily volume
        MIN_PRICE = 0.000001     # Minimum price to avoid dust tokens
        MAX_PRICE = 100000       # Maximum price to avoid extremely expensive tokens
        EXCLUDED_PATTERNS = ['UP', 'DOWN', 'BULL', 'BEAR']  # Leveraged tokens
        
        valid_count = 0
        invalid_count = 0
        processed_count = 0
        
        # Process symbols in batches to avoid overwhelming the API
        batch_size = 20
        for i in range(0, len(symbols), batch_size):
            batch_symbols = symbols[i:i + batch_size]
            
            try:
                # Get market data for this batch
                await self.rate_limiter.acquire('market_data')
                tickers = await self.market_api.get_multiple_tickers(batch_symbols)
                
                for symbol in batch_symbols:
                    processed_count += 1
                    ticker_data = tickers.get(symbol, {})
                    
                    # Validate this symbol
                    validation_result = self._validate_single_symbol(symbol, ticker_data, {
                        'min_volume_24h': MIN_VOLUME_24H,
                        'min_price': MIN_PRICE,
                        'max_price': MAX_PRICE,
                        'excluded_patterns': EXCLUDED_PATTERNS
                    })
                    
                    if validation_result['is_valid']:
                        result.add_valid_asset(symbol, validation_result['validation_data'])
                        await self._update_symbol_validation_status(symbol, True, validation_result['validation_data'])
                        valid_count += 1
                    else:
                        result.add_invalid_asset(symbol, validation_result['reason'], validation_result['validation_data'])
                        await self._update_symbol_validation_status(symbol, False, validation_result['validation_data'])
                        invalid_count += 1
                    
                    # Report progress periodically
                    if processed_count % 50 == 0:
                        await self.progress_reporter.report_item_progress(
                            f"Validando símbolos... {processed_count}/{len(symbols)} ({valid_count} válidos)",
                            processed_count, len(symbols)
                        )
                
            except Exception as e:
                logger.error(f"Error processing batch {i//batch_size + 1}: {e}")
                # Mark remaining symbols in batch as errors
                for symbol in batch_symbols[processed_count % batch_size:]:
                    result.add_error(symbol, f"Batch processing error: {str(e)}")
        
        logger.info(f"✅ Validation completed: {valid_count} valid, {invalid_count} invalid symbols")
    
    def _clean_decimal_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Decimal objects to float for JSON serialization."""
        return convert_decimals(data)
    
    def _validate_single_symbol(self, symbol: str, ticker_data: Dict[str, Any], criteria: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a single symbol against trading criteria."""
        # Clean ticker data from Decimal objects
        clean_ticker_data = self._clean_decimal_data(ticker_data)
        
        validation_data = {
            'timestamp': utc_now().isoformat(),
            'criteria_checked': list(criteria.keys()),
            'ticker_data': clean_ticker_data
        }
        
        try:
            # Check if we have ticker data
            if not clean_ticker_data:
                return {
                    'is_valid': False,
                    'reason': 'No market data available',
                    'validation_data': validation_data
                }
            
            # Extract market data - ensure all values are float
            price = float(clean_ticker_data.get('last', 0))
            volume_24h = float(clean_ticker_data.get('quoteVolume', 0))  # Volume in USDT
            symbol_clean = symbol.replace('/USDT', '').replace('USDT', '')
            
            validation_data.update({
                'price': price,
                'volume_24h': volume_24h,
                'symbol_clean': symbol_clean
            })
            
            # Validation checks
            checks = []
            
            # 1. Volume check
            if volume_24h < criteria['min_volume_24h']:
                checks.append(f"Volume too low: ${volume_24h:,.0f} < ${criteria['min_volume_24h']:,.0f}")
            else:
                checks.append("✓ Volume sufficient")
            
            # 2. Price range check
            if price < criteria['min_price']:
                checks.append(f"Price too low: ${price} < ${criteria['min_price']}")
            elif price > criteria['max_price']:
                checks.append(f"Price too high: ${price} > ${criteria['max_price']}")
            else:
                checks.append("✓ Price in acceptable range")
            
            # 3. Symbol pattern check (exclude leveraged tokens)
            excluded = False
            for pattern in criteria['excluded_patterns']:
                if pattern in symbol_clean.upper():
                    checks.append(f"Excluded pattern: contains '{pattern}'")
                    excluded = True
                    break
            if not excluded:
                checks.append("✓ Symbol pattern acceptable")
            
            # 4. Market activity check
            if ticker_data.get('bid', 0) <= 0 or ticker_data.get('ask', 0) <= 0:
                checks.append("No active bid/ask spread")
            else:
                checks.append("✓ Active market spread")
            
            validation_data['validation_checks'] = checks
            
            # Determine if valid (all checks must pass)
            failed_checks = [check for check in checks if not check.startswith('✓')]
            
            if failed_checks:
                return {
                    'is_valid': False,
                    'reason': failed_checks[0],  # Primary reason
                    'validation_data': validation_data
                }
            else:
                return {
                    'is_valid': True,
                    'reason': 'All validation criteria met',
                    'validation_data': validation_data
                }
                
        except Exception as e:
            logger.warning(f"Error validating symbol {symbol}: {e}")
            return {
                'is_valid': False,
                'reason': f'Validation error: {str(e)}',
                'validation_data': validation_data
            }
    
    async def _update_symbol_validation_status(self, symbol: str, is_valid: bool, validation_data: Dict[str, Any]) -> None:
        """Update symbol validation status in the database."""
        try:
            # Clean validation data from Decimal objects
            clean_validation_data = self._clean_decimal_data(validation_data)
            
            with get_session() as session:
                asset = session.query(Asset).filter(Asset.symbol == symbol).first()
                if asset:
                    asset.is_valid = is_valid
                    asset.last_validation = utc_now()
                    asset.validation_data = clean_validation_data
                    session.commit()
                    logger.debug(f"Updated validation for {symbol}: {'valid' if is_valid else 'invalid'}")
        except Exception as e:
            logger.error(f"Error updating validation status for {symbol}: {e}")
    
    async def get_all_symbols_data(self, include_market_data: bool = True, 
                                 max_symbols: Optional[int] = None) -> Dict[str, Any]:
        """Get comprehensive data for all symbols for the symbols table.
        
        Args:
            include_market_data: Whether to fetch current market data (price, volume, etc.)
            max_symbols: Maximum number of symbols to return (None for all)
            
        Returns:
            Dict containing formatted symbols data ready for frontend table
        """
        try:
            await self.progress_reporter.report_started(
                "Preparando dados completos dos símbolos...",
                metadata={'include_market_data': include_market_data, 'max_symbols': max_symbols}
            )
            
            with get_session() as session:
                # Get all assets from database
                all_assets = self.asset_repo.get_all(session, limit=max_symbols or 10000)
                
                if not all_assets:
                    return {
                        'symbols': [],
                        'total_count': 0,
                        'last_updated': utc_now().isoformat(),
                        'metadata': {'source': 'database', 'include_market_data': include_market_data}
                    }
                
                symbols_data = []
                processed_count = 0
                total_count = len(all_assets)
                
                # Process assets in batches for efficiency
                batch_size = 50
                for i in range(0, len(all_assets), batch_size):
                    batch_assets = all_assets[i:i + batch_size]
                    
                    if include_market_data:
                        # Get current market data for this batch
                        batch_symbols = [asset.symbol for asset in batch_assets]
                        market_data_batch = await self._get_market_data_batch(batch_symbols)
                    else:
                        market_data_batch = {}
                    
                    # Process each asset in the batch
                    for asset in batch_assets:
                        symbol_info = await self._format_symbol_data(asset, market_data_batch.get(asset.symbol))
                        symbols_data.append(symbol_info)
                        processed_count += 1
                        
                        # Report progress periodically
                        if processed_count % 100 == 0:
                            await self.progress_reporter.report_item_progress(
                                f"Processando símbolos... {processed_count}/{total_count}",
                                processed_count, total_count
                            )
                
                # Sort by symbol name for consistent display
                symbols_data.sort(key=lambda x: x['symbol'])
                
                result = {
                    'symbols': symbols_data,
                    'total_count': len(symbols_data),
                    'last_updated': utc_now().isoformat(),
                    'metadata': {
                        'source': 'database_with_live_data' if include_market_data else 'database_only',
                        'include_market_data': include_market_data,
                        'valid_count': sum(1 for s in symbols_data if s['is_valid'] is True),
                        'invalid_count': sum(1 for s in symbols_data if s['is_valid'] is False),
                        'unvalidated_count': sum(1 for s in symbols_data if s['is_valid'] is None),
                        'processing_duration_seconds': 0  # Will be updated by caller
                    }
                }
                
                await self.progress_reporter.report_completed(
                    f"✅ Dados de {len(symbols_data)} símbolos preparados com sucesso",
                    processed=len(symbols_data),
                    total=total_count,
                    **result['metadata']
                )
                
                return result
                
        except Exception as e:
            logger.error(f"Error getting symbols data: {e}")
            await self.progress_reporter.report_error(f"Erro ao preparar dados dos símbolos: {str(e)}")
            return {
                'symbols': [],
                'total_count': 0,
                'last_updated': utc_now().isoformat(),
                'error': str(e),
                'metadata': {'source': 'error', 'include_market_data': include_market_data}
            }
    
    async def _get_market_data_batch(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get current market data for a batch of symbols."""
        market_data_batch = {}
        
        try:
            # Rate limiting for API calls
            await self.rate_limiter.acquire('market_data')
            
            # Get tickers for all symbols at once (more efficient)
            tickers = await self.market_api.get_multiple_tickers(symbols)
            
            for symbol in symbols:
                ticker_data = tickers.get(symbol, {})
                if ticker_data:
                    market_data_batch[symbol] = {
                        'price': ticker_data.get('last', 0),
                        'change_24h': ticker_data.get('change', 0),
                        'change_24h_percent': ticker_data.get('percentage', 0),
                        'volume_24h': ticker_data.get('quoteVolume', 0),
                        'high_24h': ticker_data.get('high', 0),
                        'low_24h': ticker_data.get('low', 0),
                        'bid': ticker_data.get('bid', 0),
                        'ask': ticker_data.get('ask', 0),
                        'timestamp': utc_now().isoformat()
                    }
                else:
                    # Fallback with empty data
                    market_data_batch[symbol] = {
                        'price': 0,
                        'change_24h': 0,
                        'change_24h_percent': 0,
                        'volume_24h': 0,
                        'high_24h': 0,
                        'low_24h': 0,
                        'bid': 0,
                        'ask': 0,
                        'timestamp': utc_now().isoformat(),
                        'error': 'No ticker data available'
                    }
                    
        except Exception as e:
            logger.warning(f"Error fetching market data batch: {e}")
            # Return empty dict, will be handled by individual symbol processing
            
        return market_data_batch
    
    async def _format_symbol_data(self, asset: Asset, market_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Format asset data for frontend table display."""
        # Base symbol information
        symbol_info = {
            'symbol': asset.symbol,
            'base_currency': asset.base_currency,
            'quote_currency': asset.quote_currency,
            'is_valid': asset.is_valid,
            'min_order_size': float(asset.min_order_size) if asset.min_order_size else 0.0,
            'last_validation': asset.last_validation.isoformat() if asset.last_validation else None,
        }
        
        # Add market data if available
        if market_data:
            symbol_info.update({
                'current_price': market_data.get('price', 0),
                'change_24h': market_data.get('change_24h', 0),
                'change_24h_percent': market_data.get('change_24h_percent', 0),
                'volume_24h': market_data.get('volume_24h', 0),
                'high_24h': market_data.get('high_24h', 0),
                'low_24h': market_data.get('low_24h', 0),
                'bid_price': market_data.get('bid', 0),
                'ask_price': market_data.get('ask', 0),
                'market_data_timestamp': market_data.get('timestamp'),
                'has_live_data': True
            })
        else:
            # Default values when no market data
            symbol_info.update({
                'current_price': 0,
                'change_24h': 0,
                'change_24h_percent': 0,
                'volume_24h': 0,
                'high_24h': 0,
                'low_24h': 0,
                'bid_price': 0,
                'ask_price': 0,
                'market_data_timestamp': None,
                'has_live_data': False
            })
        
        # Add validation status info
        if asset.validation_data:
            validation_info = asset.validation_data
            symbol_info.update({
                'validation_reason': validation_info.get('validation_reason', ''),
                'last_error': validation_info.get('last_error', ''),
                'needs_validation': validation_info.get('needs_validation', False),
                'scan_source': validation_info.get('scan_source', 'unknown')
            })
        else:
            symbol_info.update({
                'validation_reason': '',
                'last_error': '',
                'needs_validation': True,
                'scan_source': 'unknown'
            })
        
        # Add status classification for frontend
        if asset.is_valid is True:
            symbol_info['status'] = 'valid'
            symbol_info['status_text'] = 'Válido'
            symbol_info['status_color'] = 'success'
        elif asset.is_valid is False:
            symbol_info['status'] = 'invalid'
            symbol_info['status_text'] = 'Inválido'
            symbol_info['status_color'] = 'danger'
        else:
            symbol_info['status'] = 'pending'
            symbol_info['status_text'] = 'Pendente'
            symbol_info['status_color'] = 'warning'
        
        return symbol_info

    async def get_last_scan_summary(self) -> Optional[Dict[str, Any]]:
        """Get summary of the last scan from database."""
        try:
            with get_session() as session:
                valid_assets = self.asset_repo.get_valid_assets(session)
                all_assets = self.asset_repo.get_all(session, limit=1000)
                
                if not all_assets:
                    return None
                
                # Find most recent validation timestamp
                last_validation_times = [
                    asset.last_validation for asset in all_assets 
                    if asset.last_validation
                ]
                
                if not last_validation_times:
                    return None
                
                last_scan_time = max(last_validation_times)
                
                return {
                    'last_scan_timestamp': last_scan_time.isoformat(),
                    'total_assets_in_db': len(all_assets),
                    'valid_assets_count': len(valid_assets),
                    'invalid_assets_count': len(all_assets) - len(valid_assets),
                    'valid_symbols': [asset.symbol for asset in valid_assets],
                    'needs_refresh': safe_datetime_subtract(utc_now(), last_scan_time) > 86400,  # 24 hours
                }
                
        except Exception as e:
            logger.error(f"Error getting last scan summary: {e}")
            return None
    
    async def force_revalidate_all_symbols(self) -> InitialScanResult:
        """Force revalidation of all symbols in the database with current market data."""
        logger.info("🔄 Starting forced revalidation of all symbols...")
        
        scan_start = utc_now()
        result = InitialScanResult()
        result.scan_timestamp = scan_start.isoformat()
        
        try:
            await self.progress_reporter.report_started(
                "Iniciando revalidação de todos os símbolos...",
                metadata={'mode': 'force_revalidation'}
            )
            
            # Get all symbols from database
            with get_session() as session:
                all_assets = self.asset_repo.get_all(session, limit=10000)
                
                if not all_assets:
                    await self.progress_reporter.report_error("Nenhum símbolo encontrado no banco de dados")
                    return result
                
                symbols = [asset.symbol for asset in all_assets]
                result.total_discovered = len(symbols)
                
                logger.info(f"Found {len(symbols)} symbols in database for revalidation")
                
                # Perform intelligent validation
                await self._validate_symbols_for_trading(symbols, result)
                
                # Finalize
                scan_end = utc_now()
                result.scan_duration = (scan_end - scan_start).total_seconds()
                
                await self._finalize_scan(result, scan_start, scan_end)
                return result
                
        except Exception as e:
            logger.error(f"Critical error during forced revalidation: {e}")
            await self._handle_scan_error(e, result, scan_start)
            return result
        finally:
            await self._cleanup_resources()
    
    
    def format_scan_report(self, result: InitialScanResult) -> str:
        """Format discovery results into a readable report."""
        summary = result.get_summary()
        
        report_lines = [
            "=== ASSET DISCOVERY REPORT ===",
            f"Discovery Date: {summary['scan_timestamp']}",
            f"Discovery Duration: {summary['scan_duration_seconds']:.1f} seconds",
            "",
            "=== SUMMARY ===",
            f"Total Assets Discovered: {summary['total_discovered']}",
            f"Assets Saved to Database: {summary['valid_assets_count']}",
            f"Processing Errors: {summary['errors_count']}",
            "",
            "=== NOTE ===",
            "Assets discovered need to be validated by the trading scanner.",
            "This scan only populates the database with available symbols.",
            "",
        ]
        
        if summary['valid_assets']:
            report_lines.extend([
                "=== DISCOVERED ASSETS ===",
                f"Count: {len(summary['valid_assets'])}",
                "Symbols: " + ", ".join(summary['valid_assets'][:20]),
            ])
            
            if len(summary['valid_assets']) > 20:
                report_lines.append(f"... and {len(summary['valid_assets']) - 20} more")
            
            report_lines.append("")
        
        if result.errors:
            report_lines.extend([
                "=== PROCESSING ERRORS ===",
                f"Count: {len(result.errors)}",
            ])
            
            for error in result.errors[:5]:
                report_lines.append(f"{error['symbol']}: {error['error']}")
            
            if len(result.errors) > 5:
                report_lines.append(f"... and {len(result.errors) - 5} more errors")
        
        return "\n".join(report_lines)
    
    async def _finalize_scan(self, result: InitialScanResult, scan_start: datetime, scan_end: datetime) -> None:
        """Finalize scan with comprehensive performance reporting and cleanup."""
        summary = result.get_summary()
        scan_duration = result.scan_duration
        
        # Calculate performance metrics
        throughput = result.total_discovered / scan_duration if scan_duration > 0 else 0
        avg_processing_time = scan_duration / max(result.total_discovered, 1)
        cache_hit_rate = (self._scan_stats['cache_hits'] / max(self._scan_stats['api_calls'], 1)) * 100
        
        # Enhanced completion metadata with performance insights
        completion_metadata = {
            'mode': 'fetch_and_populate',
            'config_used': self.config.to_dict(),
            'scan_stats': self._scan_stats,
            'discovered_assets_count': len(result.valid_assets),
            'total_assets': result.total_discovered,
            'scan_duration_seconds': scan_duration,
            'success_rate_percent': summary['success_rate'],
            'throughput_assets_per_second': round(throughput, 2),
            'avg_processing_time_ms': round(avg_processing_time * 1000, 2),
            'cache_hit_rate_percent': round(cache_hit_rate, 2),
            'memory_efficiency': self._calculate_memory_efficiency(),
            'error_rate_percent': (len(self._scan_stats['errors']) / max(result.total_discovered, 1)) * 100
        }
        
        await self.progress_reporter.report_completed(
            f"🔍 Descoberta de ativos concluída! {summary['valid_assets_count']} "
            f"ativos descobertos em {scan_duration:.1f}s "
            f"({throughput:.1f} ativos/s) - prontos para validação pelo trading scanner",
            processed=summary['valid_assets_count'],
            total=summary['total_discovered'],
            **completion_metadata
        )
        
        # Comprehensive performance logging
        logger.info(
            f"🚀 Asset discovery completed:\n"
            f"  ├─ Assets discovered: {summary['valid_assets_count']}/{summary['total_discovered']}\n"
            f"  ├─ Duration: {summary['scan_duration_seconds']:.1f}s ({throughput:.1f} assets/s)\n"
            f"  ├─ Mode: Discovery only (validation by trading scanner)\n"
            f"  ├─ Performance: {avg_processing_time*1000:.1f}ms avg/asset, {cache_hit_rate:.1f}% cache hit rate\n"
            f"  └─ Memory: {completion_metadata['memory_efficiency']:.1f}% efficiency"
        )
        
        # Error analysis and logging
        if self._scan_stats['errors']:
            error_count = len(self._scan_stats['errors'])
            error_rate = (error_count / max(result.total_discovered, 1)) * 100
            logger.warning(
                f"⚠️  Discovery completed with {error_count} errors ({error_rate:.1f}% error rate):\n"
                f"  └─ Sample errors: {self._scan_stats['errors'][:3]}"
            )
        
        # Performance recommendations
        if cache_hit_rate < 50:
            logger.info("💡 Performance tip: Consider increasing cache TTL for better hit rates")
        if throughput < 10:
            logger.info("💡 Performance tip: Discovery is running slower than expected")
        if avg_processing_time > 1.0:
            logger.info("💡 Performance tip: API response times are high, check network/rate limits")
    
    def _calculate_memory_efficiency(self) -> float:
        """Calculate memory efficiency based on cache and processing metrics."""
        try:
            import psutil
            import os
            
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            
            # Calculate efficiency based on RSS memory usage per processed asset
            memory_per_asset = memory_info.rss / max(self._scan_stats['total_processed'], 1)
            
            # Normalize to percentage (lower memory per asset = higher efficiency)
            # Assume 10MB per asset as baseline (0% efficiency)
            baseline_memory = 10 * 1024 * 1024  # 10MB
            efficiency = max(0, min(100, (1 - memory_per_asset / baseline_memory) * 100))
            
            return efficiency
            
        except (ImportError, Exception):
            # Fallback calculation based on cache statistics
            cache_efficiency = min(100, self._scan_stats.get('cache_hits', 0) / max(self._scan_stats.get('api_calls', 1), 1) * 100)
            return cache_efficiency
    
    async def _handle_scan_error(self, error: Exception, result: InitialScanResult, scan_start: datetime) -> None:
        """Handle critical scan errors with proper cleanup and reporting."""
        result.add_error("CRITICAL_SCAN_ERROR", str(error))
        result.scan_duration = (utc_now() - scan_start).total_seconds()
        
        error_metadata = {
            'error_type': type(error).__name__,
            'scan_stats': self._scan_stats,
            'mode': 'discovery_only'
        }
        
        await self.progress_reporter.report_error(
            f"Erro crítico durante o scan: {str(error)}",
            **error_metadata
        )
    
    async def _cleanup_resources(self) -> None:
        """Comprehensive resource cleanup with memory optimization."""
        try:
            import gc
            import weakref
            
            # Clean up cache and connections
            if hasattr(self.cache, 'cleanup'):
                await self.cache.cleanup()
            
            # Clean up rate limiter resources
            if hasattr(self.rate_limiter, 'cleanup'):
                await self.rate_limiter.cleanup()
            
            # Force garbage collection of large objects
            collected = gc.collect()
            
            # Reset statistics for next scan
            self._scan_stats = {
                'total_processed': 0,
                'successful_discoveries': 0,
                'failed_discoveries': 0,
                'cache_hits': 0,
                'api_calls': 0,
                'errors': []
            }
            
            logger.debug(f"Scanner resources cleaned up successfully (GC collected {collected} objects)")
            
        except Exception as e:
            logger.warning(f"Error during resource cleanup: {e}")
        
        finally:
            # Ensure cleanup always completes
            try:
                # Clear any remaining references
                if hasattr(self, '_temp_data'):
                    delattr(self, '_temp_data')
            except:
                pass


# Global initial scanner instance
_initial_scanner = None


def get_initial_scanner() -> InitialScanner:
    """Get the global InitialScanner instance."""
    global _initial_scanner
    if _initial_scanner is None:
        _initial_scanner = InitialScanner()
    return _initial_scanner


# Convenience functions for standalone scanning
async def perform_initial_scan(max_assets: Optional[int] = None, 
                             force_refresh: bool = False) -> InitialScanResult:
    """Perform initial asset scan and return results."""
    scanner = get_initial_scanner()
    return await scanner.scan_all_assets(force_refresh=force_refresh, max_assets=max_assets)


async def perform_symbol_revalidation() -> InitialScanResult:
    """Force revalidation of all symbols in database with current market data."""
    scanner = get_initial_scanner()
    return await scanner.force_revalidate_all_symbols()


async def main():
    """Main entry point for running initial scanner."""
    import sys
    from database.connection import init_database, create_tables
    
    try:
        print("🚀 Iniciando Scanner Inicial BingX...")
        
        # Inicializar banco de dados
        print("📋 Inicializando banco de dados...")
        if not init_database():
            print("❌ ERRO: Falha ao inicializar banco de dados")
            print("💡 Verifique as variáveis de ambiente DB_*")
            sys.exit(1)
        
        if not create_tables():
            print("❌ ERRO: Falha ao criar tabelas")
            sys.exit(1)
        
        print("✅ Banco de dados inicializado")
        
        # Executar scan inicial
        print("🔍 Executando descoberta inicial de todos os ativos...")
        result = await perform_initial_scan(force_refresh=True)
        
        # Exibir resultados
        summary = result.get_summary()
        print(f"\n📊 RESULTADOS DA DESCOBERTA:")
        print(f"   • Total descobertos: {summary['total_discovered']}")
        print(f"   • Ativos salvos no banco: {summary['valid_assets_count']}")
        print(f"   • Erros de processamento: {summary['errors_count']}")
        print(f"   • Duração: {summary['scan_duration_seconds']:.1f}s")
        
        if summary['valid_assets']:
            print(f"\n✅ ATIVOS DESCOBERTOS ({len(summary['valid_assets'])}):")
            for symbol in summary['valid_assets'][:10]:  # Primeiros 10
                print(f"   • {symbol}")
            if len(summary['valid_assets']) > 10:
                print(f"   • ... e mais {len(summary['valid_assets']) - 10} ativos")
        
        if result.errors:
            print(f"\n⚠️ ERROS DE PROCESSAMENTO ({len(result.errors)}):")
            for error in result.errors[:5]:  # Primeiros 5 erros
                print(f"   • {error['symbol']}: {error['error']}")
        
        print(f"\n🎉 Descoberta concluída! {summary['valid_assets_count']} ativos salvos no banco.")
        print("💡 Use o trading scanner para validar e monitorar os ativos.")
        
    except Exception as e:
        print(f"❌ ERRO CRÍTICO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())