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
from scanner.validator import get_asset_validator
from config.trading_config import TradingConfig
from utils.logger import get_logger, trading_logger
from utils.formatters import DataFormatter
from utils.datetime_utils import utc_now, safe_datetime_subtract
from utils.rate_limiter import get_rate_limiter
from utils.smart_cache import get_smart_cache
from api.web_api import manager as connection_manager

# New imports for improved patterns
from scanner.scanner_config import get_scanner_config, ScannerConfig
from scanner.progress_observers import (
    ProgressReporter, CompositeProgressObserver, WebSocketProgressObserver, 
    LoggingProgressObserver, ProgressEvent
)
from scanner.validation_strategy import (
    ValidationStrategyFactory, ValidationStrategy, ValidationResult
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
    """Performs initial discovery and validation of all available trading assets.
    
    Improved implementation using:
    - Configuration management for all settings
    - Observer pattern for progress reporting
    - Strategy pattern for validation approaches
    - Better error handling and resource management
    """
    
    def __init__(self, config: Optional[ScannerConfig] = None, 
                 validation_strategy: Optional[ValidationStrategy] = None,
                 progress_reporter: Optional[ProgressReporter] = None):
        # Core dependencies (unchanged)
        self.market_api = get_market_data_api()
        self.validator = get_asset_validator()
        self.asset_repo = AssetRepository()
        self.client = get_client()
        self.rate_limiter = get_rate_limiter()
        self.cache = get_smart_cache()
        
        # New pattern-based components
        self.config = config or get_scanner_config()
        self.validation_strategy = validation_strategy or ValidationStrategyFactory.get_default_strategy()
        
        # Setup progress reporting with multiple observers
        if progress_reporter is None:
            composite_observer = CompositeProgressObserver()
            composite_observer.add_observer(WebSocketProgressObserver(connection_manager))
            composite_observer.add_observer(LoggingProgressObserver(logger))
            self.progress_reporter = ProgressReporter(composite_observer)
        else:
            self.progress_reporter = progress_reporter
        
        # Performance tracking
        self._scan_stats = {
            'total_processed': 0,
            'successful_validations': 0,
            'failed_validations': 0,
            'cache_hits': 0,
            'api_calls': 0,
            'errors': []
        }
        
    async def scan_all_assets(self, force_refresh: bool = False, 
                            max_assets: Optional[int] = None,
                            validation_strategy_name: Optional[str] = None) -> InitialScanResult:
        """Perform complete initial scan of all available assets.
        
        Args:
            force_refresh: Force refresh of cached market data
            max_assets: Maximum number of assets to process (None for all)
            validation_strategy_name: Name of validation strategy to use
            
        Returns:
            InitialScanResult containing scan results and statistics
        """
        scan_start = utc_now()
        result = InitialScanResult()
        result.scan_timestamp = scan_start.isoformat()
        
        # Override validation strategy if specified
        if validation_strategy_name:
            try:
                self.validation_strategy = ValidationStrategyFactory.create_strategy(validation_strategy_name)
                logger.info(f"Using validation strategy: {validation_strategy_name}")
            except ValueError as e:
                logger.warning(f"Invalid strategy name '{validation_strategy_name}': {e}")
        
        try:
            await self.progress_reporter.report_started(
                "Iniciando scan inicial de ativos...",
                metadata={
                    'force_refresh': force_refresh,
                    'max_assets': max_assets,
                    'strategy': self.validation_strategy.get_strategy_name(),
                    'config': self.config.to_dict()
                }
            )
            
            # Template method pattern: define the scan process steps
            markets = await self._discover_markets_step(force_refresh)
            if not markets:
                await self.progress_reporter.report_error("Nenhum mercado descoberto")
                return result
            
            symbols = await self._extract_symbols_step(markets, max_assets)
            result.total_discovered = len(symbols)
            
            validation_results = await self._validate_assets_step(symbols)
            await self._save_results_step(validation_results)
            await self._process_results_step(validation_results, result)
            
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

        # Sort to prioritize important assets using configuration
        if self.config.enable_priority_processing:
            return self._prioritize_symbols(symbols)
        else:
            return sorted(symbols)
    
    def _prioritize_symbols(self, symbols: List[str]) -> List[str]:
        """Prioritize symbols based on validator criteria."""
        priority_symbols = []
        other_symbols = []
        
        priority_list = getattr(self.validator.criteria, 'PRIORITY_SYMBOLS', [])
        
        for symbol in symbols:
            if symbol in priority_list:
                priority_symbols.append(symbol)
            else:
                other_symbols.append(symbol)
        
        logger.info(f"Prioritized {len(priority_symbols)} priority symbols, {len(other_symbols)} regular symbols")
        
        # Return priority symbols first, then others
        return priority_symbols + sorted(other_symbols)
    
    async def _validate_assets_step(self, symbols: List[str]) -> List[ValidationResult]:
        """Step 3: Validate all discovered assets using selected strategy."""
        await self.progress_reporter.report_step_progress(
            f"Validando {len(symbols)} ativos usando estratégia {self.validation_strategy.get_strategy_name()}...",
            3, self.config.broadcast_progress_steps
        )
        
        try:
            # Use the selected validation strategy
            validation_results = await self.validation_strategy.validate_symbols(
                symbols, self.validator, progress_reporter=self.progress_reporter
            )
            
            # Update statistics
            self._scan_stats['total_processed'] = len(validation_results)
            self._scan_stats['successful_validations'] = sum(1 for r in validation_results if r.is_valid)
            self._scan_stats['failed_validations'] = sum(1 for r in validation_results if not r.is_valid)
            
            logger.info(f"Validation completed: {self._scan_stats['successful_validations']} valid, "
                       f"{self._scan_stats['failed_validations']} invalid")
            
            return validation_results
            
        except Exception as e:
            logger.error(f"Critical error during asset validation: {e}")
            self._scan_stats['errors'].append(f"Validation failed: {str(e)}")
            raise
    
    # Legacy method removed - now using ValidationStrategy pattern
    # This method has been replaced by _validate_assets_step() and the Strategy pattern
    
    async def _save_results_step(self, validation_results: List[ValidationResult]) -> None:
        """Step 4: Save validation results to database efficiently."""
        await self.progress_reporter.report_step_progress(
            "Salvando resultados no banco de dados...", 4, self.config.broadcast_progress_steps
        )
        
        if not validation_results:
            logger.warning("No validation results to save")
            return
            
        try:
            from utils.converters import convert_decimals
            
            # Process in batches for better memory usage
            batch_size = self.config.db_batch_size
            total_saved = 0
            
            for i in range(0, len(validation_results), batch_size):
                batch = validation_results[i:i + batch_size]
                await self._save_validation_batch(batch)
                total_saved += len(batch)
                
                # Report progress for large datasets
                if len(validation_results) > 100 and total_saved % self.config.progress_report_interval == 0:
                    await self.progress_reporter.report_item_progress(
                        f"Salvando resultados... {total_saved}/{len(validation_results)}",
                        total_saved, len(validation_results)
                    )
            
            logger.info(f"Successfully saved {total_saved} validation results to database")
            
        except Exception as e:
            logger.error(f"Critical error saving validation results: {e}")
            self._scan_stats['errors'].append(f"Database save failed: {str(e)}")
            raise
    
    async def _save_validation_batch(self, batch: List[ValidationResult]) -> None:
        """Optimized batch save with better database performance and memory management."""
        from utils.converters import convert_decimals
        import gc
        
        if not batch:
            return
            
        bulk_update_data = []
        bulk_insert_data = []
        priority_list = getattr(self.validator.criteria, 'PRIORITY_SYMBOLS', [])
        
        # Pre-allocate lists for better memory efficiency
        batch_size = len(batch)
        bulk_update_data.reserve = batch_size if hasattr(list, 'reserve') else None
        bulk_insert_data.reserve = batch_size if hasattr(list, 'reserve') else None
        
        # Process batch with memory-efficient iteration
        for result in batch:
            try:
                is_valid = result.is_valid
                validation_data = convert_decimals(result.validation_data or {})
                
                # Optimized validation data structure
                db_validation_data = {
                    'validation_timestamp': result.validation_timestamp.isoformat(),
                    'validation_duration': result.validation_duration_seconds,
                    'validation_checks': validation_data.get('validation_checks', {}),
                    'market_summary': validation_data.get('market_summary', {}),
                    'volume_analysis': validation_data.get('volume_analysis', {}),
                    'priority': result.symbol in priority_list,
                    'is_valid': is_valid,
                    'reason': result.reason if not is_valid else None,
                    'retry_count': result.retry_count,
                    'strategy_used': self.validation_strategy.get_strategy_name()
                }
                
                bulk_update_data.append({
                    'symbol': result.symbol,
                    'is_valid': is_valid,
                    'validation_data': db_validation_data
                })
                
                # Prepare asset creation data if needed (optimized parsing)
                if '/' in result.symbol:
                    try:
                        symbol_parts = result.symbol.split('/', 1)  # Limit split for performance
                        if len(symbol_parts) == 2:
                            base_currency, quote_currency = symbol_parts
                            
                            market_summary = validation_data.get('market_summary', {})
                            min_order_size = market_summary.get('quote_volume_24h', TradingConfig.MIN_ORDER_SIZE_USDT)
                            
                            # Optimized number conversion
                            if isinstance(min_order_size, (int, float)):
                                min_order_size = min(float(min_order_size) / 1000, float(TradingConfig.MIN_ORDER_SIZE_USDT))
                            elif isinstance(min_order_size, str):
                                try:
                                    min_order_size = min(float(min_order_size) / 1000, float(TradingConfig.MIN_ORDER_SIZE_USDT))
                                except ValueError:
                                    min_order_size = float(TradingConfig.MIN_ORDER_SIZE_USDT)
                            else:
                                min_order_size = float(TradingConfig.MIN_ORDER_SIZE_USDT)
                            
                            bulk_insert_data.append({
                                'symbol': result.symbol,
                                'base_currency': base_currency,
                                'quote_currency': quote_currency,
                                'is_valid': is_valid,
                                'min_order_size': min_order_size,
                                'last_validation': utc_now(),
                                'validation_data': db_validation_data
                            })
                    except Exception as prep_error:
                        logger.warning(f"Could not prepare asset data for {result.symbol}: {prep_error}")
                        
                # Clear reference to help with memory management
                validation_data = None
                db_validation_data = None
                
            except Exception as process_error:
                logger.error(f"Error processing validation result for {result.symbol}: {process_error}")
                continue
        
        # Optimized database operations with transaction management
        try:
            with get_session() as session:
                # Begin transaction explicitly for better control
                session.begin()
                
                try:
                    # Batch update existing records (more efficient)
                    update_count = 0
                    for update_data in bulk_update_data:
                        try:
                            success = self.asset_repo.update_validation_status(
                                session,
                                symbol=update_data['symbol'],
                                is_valid=update_data['is_valid'],
                                validation_data=update_data['validation_data']
                            )
                            if success:
                                update_count += 1
                        except Exception as update_error:
                            logger.warning(f"Could not update validation for {update_data['symbol']}: {update_error}")
                    
                    # Batch create new records (check existence first for efficiency)
                    existing_symbols = set()
                    if bulk_insert_data:
                        # Query existing symbols in batch
                        symbols_to_check = [item['symbol'] for item in bulk_insert_data]
                        existing_assets = session.query(self.asset_repo.model.symbol).filter(
                            self.asset_repo.model.symbol.in_(symbols_to_check)
                        ).all()
                        existing_symbols = {asset.symbol for asset in existing_assets}
                    
                    insert_count = 0
                    for insert_data in bulk_insert_data:
                        if insert_data['symbol'] not in existing_symbols:
                            try:
                                self.asset_repo.create(session, **insert_data)
                                insert_count += 1
                            except Exception as insert_error:
                                logger.warning(f"Could not create asset {insert_data['symbol']}: {insert_error}")
                    
                    # Commit transaction
                    session.commit()
                    logger.debug(f"Batch database operation completed: {update_count} updates, {insert_count} inserts")
                    
                except Exception as transaction_error:
                    session.rollback()
                    logger.error(f"Database transaction failed, rolled back: {transaction_error}")
                    raise
                    
        except Exception as db_error:
            logger.error(f"Database batch operation failed: {db_error}")
            # Don't raise - allow scan to continue with other batches
        
        finally:
            # Explicit memory cleanup for large batches
            if batch_size > 100:
                bulk_update_data.clear()
                bulk_insert_data.clear()
                gc.collect()

    # Legacy method removed - now handled by ValidationStrategy implementations
    # Caching and optimization logic moved to individual strategy classes
    
    async def _bulk_save_validation_results(self, validation_data_list: List[Tuple[str, Dict[str, Any]]]):
        """Save multiple validation results in a single database transaction."""
        if not validation_data_list:
            return
            
        try:
            from utils.converters import convert_decimals
            
            # Prepare all data for bulk insert/update
            bulk_update_data = []
            bulk_insert_data = []
            
            for symbol, validation_result in validation_data_list:
                is_valid = validation_result.get('is_valid', False)
                validation_data = convert_decimals(validation_result.get('data', {}))
                
                # Enhanced validation data with metadata
                db_validation_data = {
                    'validation_timestamp': validation_result.get('validation_timestamp'),
                    'validation_duration': validation_result.get('validation_duration_seconds', 0),
                    'validation_checks': validation_data.get('validation_checks', {}),
                    'market_summary': validation_data.get('market_summary', {}),
                    'volume_analysis': validation_data.get('volume_analysis', {}),
                    'priority': symbol in self.validator.criteria.PRIORITY_SYMBOLS,
                    'is_valid': is_valid,
                    'reason': validation_result.get('reason') if not is_valid else None
                }
                
                # Prepare for bulk operations
                bulk_update_data.append({
                    'symbol': symbol,
                    'is_valid': is_valid,
                    'validation_data': db_validation_data
                })
                
                # Prepare asset creation data if needed
                if '/' in symbol:
                    try:
                        base_currency, quote_currency = symbol.split('/')
                        market_summary = validation_data.get('market_summary', {})
                        min_order_size = market_summary.get('quote_volume_24h', TradingConfig.MIN_ORDER_SIZE_USDT)
                        if isinstance(min_order_size, (int, float, str)):
                            min_order_size = min(float(min_order_size) / 1000, float(TradingConfig.MIN_ORDER_SIZE_USDT))
                        
                        bulk_insert_data.append({
                            'symbol': symbol,
                            'base_currency': base_currency,
                            'quote_currency': quote_currency,
                            'is_valid': is_valid,
                            'min_order_size': min_order_size,
                            'last_validation': utc_now(),
                            'validation_data': db_validation_data
                        })
                    except Exception as prep_error:
                        logger.warning(f"Could not prepare asset data for {symbol}: {prep_error}")
            
            # Execute bulk operations in a single transaction
            with get_session() as session:
                # Bulk update validation statuses
                for update_data in bulk_update_data:
                    try:
                        self.asset_repo.update_validation_status(
                            session,
                            symbol=update_data['symbol'],
                            is_valid=update_data['is_valid'],
                            validation_data=update_data['validation_data']
                        )
                    except Exception as update_error:
                        logger.warning(f"Could not update validation for {update_data['symbol']}: {update_error}")
                
                # Bulk create assets that don't exist
                for insert_data in bulk_insert_data:
                    try:
                        existing = self.asset_repo.get_by_symbol(session, insert_data['symbol'])
                        if not existing:
                            self.asset_repo.create(session, **insert_data)
                    except Exception as insert_error:
                        logger.warning(f"Could not create asset {insert_data['symbol']}: {insert_error}")
                
                # Commit all changes in one transaction
                session.commit()
                
            logger.debug(f"Bulk saved {len(validation_data_list)} validation results")
            
        except Exception as e:
            logger.error(f"Failed to bulk save validation results: {e}")
            # Fallback to individual saves if bulk fails
            for symbol, validation_result in validation_data_list:
                try:
                    await self._save_validation_result_to_db(symbol, validation_result)
                except Exception as fallback_error:
                    logger.error(f"Fallback save failed for {symbol}: {fallback_error}")
    
    async def _save_validation_result_to_db(self, symbol: str, validation_result: Dict[str, Any]):
        """Save a single validation result to database (fallback method)."""
        try:
            # Import convert_decimals utility function
            from utils.converters import convert_decimals
            
            # Prepare validation data for database
            is_valid = validation_result.get('is_valid', False)
            validation_data = convert_decimals(validation_result.get('data', {}))
            
            # Enhanced validation data with metadata
            db_validation_data = {
                'validation_timestamp': validation_result.get('validation_timestamp'),
                'validation_duration': validation_result.get('validation_duration_seconds', 0),
                'validation_checks': validation_data.get('validation_checks', {}),
                'market_summary': validation_data.get('market_summary', {}),
                'volume_analysis': validation_data.get('volume_analysis', {}),
                'priority': symbol in self.validator.criteria.PRIORITY_SYMBOLS,
                'is_valid': is_valid,
                'reason': validation_result.get('reason') if not is_valid else None
            }
            
            # Save to database in its own transaction
            with get_session() as session:
                # Update or create asset with validation status
                asset = self.asset_repo.update_validation_status(
                    session,
                    symbol=symbol,
                    is_valid=is_valid,
                    validation_data=db_validation_data
                )
                
                # If asset was created/updated successfully and doesn't exist, create the base record
                if asset and not self.asset_repo.get_by_symbol(session, symbol):
                    try:
                        base_currency, quote_currency = symbol.split('/')
                        
                        # Get minimum order size from market data if available
                        market_summary = validation_data.get('market_summary', {})
                        min_order_size = market_summary.get('quote_volume_24h', TradingConfig.MIN_ORDER_SIZE_USDT)
                        if isinstance(min_order_size, (int, float, str)):
                            min_order_size = min(float(min_order_size) / 1000, float(TradingConfig.MIN_ORDER_SIZE_USDT))
                        
                        self.asset_repo.create(
                            session,
                            symbol=symbol,
                            base_currency=base_currency,
                            quote_currency=quote_currency,
                            is_valid=is_valid,
                            min_order_size=min_order_size,
                            last_validation=utc_now(),
                            validation_data=db_validation_data
                        )
                        
                    except Exception as create_error:
                        logger.warning(f"Could not create asset record for {symbol}: {create_error}")
                        # Continue anyway as the validation status was saved
                
                # Commit the transaction
                session.commit()
                
                logger.debug(f"Saved {'valid' if is_valid else 'invalid'} asset {symbol} to database")
                
        except Exception as e:
            logger.error(f"Failed to save validation result for {symbol}: {e}")
            # Don't raise the exception - let the scan continue with other assets
            pass
    
    async def _process_results_step(self, validation_results: List[ValidationResult], 
                                  result: InitialScanResult) -> None:
        """Step 5: Process validation results and populate scan result."""
        await self.progress_reporter.report_step_progress(
            "Processando resultados finais...", 5, self.config.broadcast_progress_steps
        )
        
        for validation_result in validation_results:
            try:
                if validation_result.is_valid:
                    result.add_valid_asset(validation_result.symbol, validation_result.validation_data or {})
                else:
                    reason = validation_result.reason or 'Unknown validation failure'
                    result.add_invalid_asset(validation_result.symbol, reason, validation_result.validation_data or {})
                    
            except Exception as e:
                logger.error(f"Error processing validation result for {validation_result.symbol}: {e}")
                result.add_error(validation_result.symbol, str(e))
                self._scan_stats['errors'].append(f"Result processing failed for {validation_result.symbol}: {str(e)}")
    
    
    
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
    
    async def quick_validation_check(self, symbols: List[str]) -> Dict[str, bool]:
        """Perform quick validation check on specific symbols."""
        logger.info(f"Performing quick validation check on {len(symbols)} symbols")
        
        results = {}
        
        try:
            validation_results = await self.validator.validate_multiple_assets(symbols, max_concurrent=5)
            
            for symbol, validation_data in validation_results.items():
                results[symbol] = validation_data.get('is_valid', False)
            
            valid_count = sum(results.values())
            logger.info(f"Quick validation complete: {valid_count}/{len(symbols)} symbols valid")
            
            return results
            
        except Exception as e:
            logger.error(f"Error during quick validation check: {e}")
            return {symbol: False for symbol in symbols}
    
    def format_scan_report(self, result: InitialScanResult) -> str:
        """Format scan results into a readable report."""
        summary = result.get_summary()
        
        report_lines = [
            "=== INITIAL ASSET SCAN REPORT ===",
            f"Scan Date: {summary['scan_timestamp']}",
            f"Scan Duration: {summary['scan_duration_seconds']:.1f} seconds",
            "",
            "=== SUMMARY ===",
            f"Total Assets Discovered: {summary['total_discovered']}",
            f"Valid Assets: {summary['valid_assets_count']} ({summary['success_rate']:.1f}%)",
            f"Invalid Assets: {summary['invalid_assets_count']}",
            f"Errors: {summary['errors_count']}",
            "",
        ]
        
        if summary['valid_assets']:
            report_lines.extend([
                "=== VALID ASSETS ===",
                f"Count: {len(summary['valid_assets'])}",
                "Symbols: " + ", ".join(summary['valid_assets'][:20]),
            ])
            
            if len(summary['valid_assets']) > 20:
                report_lines.append(f"... and {len(summary['valid_assets']) - 20} more")
            
            report_lines.append("")
        
        if summary['top_invalid_reasons']:
            report_lines.extend([
                "=== TOP REJECTION REASONS ===",
            ])
            
            for reason, count in summary['top_invalid_reasons']:
                report_lines.append(f"{reason}: {count} assets")
            
            report_lines.append("")
        
        if result.errors:
            report_lines.extend([
                "=== ERRORS ===",
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
        avg_validation_time = scan_duration / max(result.total_discovered, 1)
        cache_hit_rate = (self._scan_stats['cache_hits'] / max(self._scan_stats['api_calls'], 1)) * 100
        
        # Enhanced completion metadata with performance insights
        completion_metadata = {
            'strategy_used': self.validation_strategy.get_strategy_name(),
            'config_used': self.config.to_dict(),
            'scan_stats': self._scan_stats,
            'valid_assets_count': len(result.valid_assets),
            'invalid_assets_count': len(result.invalid_assets),
            'total_assets': result.total_discovered,
            'scan_duration_seconds': scan_duration,
            'success_rate_percent': summary['success_rate'],
            'throughput_assets_per_second': round(throughput, 2),
            'avg_validation_time_ms': round(avg_validation_time * 1000, 2),
            'cache_hit_rate_percent': round(cache_hit_rate, 2),
            'memory_efficiency': self._calculate_memory_efficiency(),
            'error_rate_percent': (len(self._scan_stats['errors']) / max(result.total_discovered, 1)) * 100
        }
        
        await self.progress_reporter.report_completed(
            f"⚡ Scan otimizado concluído! {summary['valid_assets_count']}/{summary['total_discovered']} "
            f"ativos válidos ({summary['success_rate']:.1f}% sucesso) em {scan_duration:.1f}s "
            f"({throughput:.1f} ativos/s)",
            processed=summary['valid_assets_count'],
            total=summary['total_discovered'],
            **completion_metadata
        )
        
        # Comprehensive performance logging
        logger.info(
            f"🚀 High-performance initial scan completed:\n"
            f"  ├─ Assets: {summary['valid_assets_count']}/{summary['total_discovered']} valid ({summary['success_rate']:.1f}% success)\n"
            f"  ├─ Duration: {summary['scan_duration_seconds']:.1f}s ({throughput:.1f} assets/s)\n"
            f"  ├─ Strategy: {self.validation_strategy.get_strategy_name()}\n"
            f"  ├─ Performance: {avg_validation_time*1000:.1f}ms avg/asset, {cache_hit_rate:.1f}% cache hit rate\n"
            f"  └─ Memory: {completion_metadata['memory_efficiency']:.1f}% efficiency"
        )
        
        # Error analysis and logging
        if self._scan_stats['errors']:
            error_count = len(self._scan_stats['errors'])
            error_rate = (error_count / max(result.total_discovered, 1)) * 100
            logger.warning(
                f"⚠️  Scan completed with {error_count} errors ({error_rate:.1f}% error rate):\n"
                f"  └─ Sample errors: {self._scan_stats['errors'][:3]}"
            )
        
        # Performance recommendations
        if cache_hit_rate < 50:
            logger.info("💡 Performance tip: Consider increasing cache TTL for better hit rates")
        if throughput < 5:
            logger.info("💡 Performance tip: Consider using high_performance validation strategy")
        if avg_validation_time > 2.0:
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
            'strategy_used': self.validation_strategy.get_strategy_name()
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
            
            # Clear validation strategy resources
            if hasattr(self.validation_strategy, 'cleanup'):
                await self.validation_strategy.cleanup()
            
            # Force garbage collection of large objects
            collected = gc.collect()
            
            # Reset statistics for next scan (keep some for monitoring)
            self._scan_stats = {
                'total_processed': 0,
                'successful_validations': 0,
                'failed_validations': 0,
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


# Convenience function for standalone scanning
async def perform_initial_scan(max_assets: Optional[int] = None, 
                             force_refresh: bool = False) -> InitialScanResult:
    """Perform initial asset scan and return results."""
    scanner = get_initial_scanner()
    return await scanner.scan_all_assets(force_refresh=force_refresh, max_assets=max_assets)


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
        print("🔍 Executando scan inicial de todos os ativos...")
        result = await perform_initial_scan(force_refresh=True)
        
        # Exibir resultados
        summary = result.get_summary()
        print(f"\n📊 RESULTADOS DO SCAN:")
        print(f"   • Total descobertos: {summary['total_discovered']}")
        print(f"   • Ativos válidos: {summary['valid_assets_count']}")
        print(f"   • Ativos inválidos: {summary['invalid_assets_count']}")
        print(f"   • Taxa de sucesso: {summary['success_rate']:.1f}%")
        print(f"   • Duração: {summary['scan_duration_seconds']:.1f}s")
        
        if summary['valid_assets']:
            print(f"\n✅ ATIVOS VÁLIDOS ({len(summary['valid_assets'])}):")
            for symbol in summary['valid_assets'][:10]:  # Primeiros 10
                print(f"   • {symbol}")
            if len(summary['valid_assets']) > 10:
                print(f"   • ... e mais {len(summary['valid_assets']) - 10} ativos")
        
        if result.errors:
            print(f"\n⚠️ ERROS ({len(result.errors)}):")
            for error in result.errors[:5]:  # Primeiros 5 erros
                print(f"   • {error['symbol']}: {error['error']}")
        
        print(f"\n🎉 Scan concluído! {summary['valid_assets_count']} ativos prontos para trading.")
        
    except Exception as e:
        print(f"❌ ERRO CRÍTICO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())