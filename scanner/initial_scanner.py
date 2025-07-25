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
    """Performs initial discovery and validation of all available trading assets."""
    
    def __init__(self):
        self.market_api = get_market_data_api()
        self.validator = get_asset_validator()
        self.asset_repo = AssetRepository()
        self.client = get_client()
        self.rate_limiter = get_rate_limiter()
        self.cache = get_smart_cache()
        
    async def scan_all_assets(self, force_refresh: bool = False, 
                            max_assets: Optional[int] = None) -> InitialScanResult:
        """Perform complete initial scan of all available assets."""
        logger.info("Starting initial asset scan...")
        scan_start = utc_now()
        result = InitialScanResult()
        result.scan_timestamp = scan_start.isoformat()
        
        try:
            # Step 1: Discover all available markets
            logger.info("Discovering available markets...")
            await self._broadcast_progress("Descobrindo mercados disponíveis...", 0, 5)
            markets = await self._discover_markets(force_refresh)
            
            if not markets:
                logger.error("No markets discovered")
                return result
            
            # Step 2: Filter markets - PEGAR TODOS OS ATIVOS SEM LIMITAÇÃO
            await self._broadcast_progress("Filtrando pares USDT...", 1, 5)
            usdt_symbols = self._extract_usdt_symbols(markets)
            
            # Remover limitação de max_assets - sempre processar TODOS
            if max_assets and max_assets > 0:
                logger.info(f"Max assets parameter provided ({max_assets}), but processing ALL {len(usdt_symbols)} assets")
            else:
                logger.info(f"Processing ALL {len(usdt_symbols)} assets - no limits applied")
            
            result.total_discovered = len(usdt_symbols)
            logger.info(f"Discovered {result.total_discovered} USDT pairs for validation")
            
            # Step 3: Validate all discovered assets
            await self._broadcast_progress(f"Validando {result.total_discovered} ativos...", 2, 5)
            all_validation_results = await self._validate_discovered_assets(usdt_symbols)
            
            # Step 4: Save all collected results to database
            await self._broadcast_progress("Salvando resultados no banco...", 3, 5)
            await self._save_all_collected_results(all_validation_results)
            
            # Step 5: Process validation results for summary
            await self._broadcast_progress("Processando resultados finais...", 4, 5)
            await self._process_validation_results(dict(all_validation_results), result)
            
            # Calculate final metrics
            scan_end = utc_now()
            result.scan_duration = (scan_end - scan_start).total_seconds()
            
            # Broadcast completion to frontend
            completion_message = {
                "type": "scanner_completion",
                "payload": {
                    "status": "completed",
                    "total_assets": result.total_discovered,
                    "valid_assets_count": len(result.valid_assets),
                    "invalid_assets_count": len(result.invalid_assets),
                    "scan_duration_seconds": result.scan_duration,
                    "timestamp": utc_now().isoformat()
                }
            }
            await connection_manager.broadcast(completion_message)
            
            # Log summary
            summary = result.get_summary()
            logger.info(f"Initial scan completed: {summary['valid_assets_count']}/{summary['total_discovered']} "
                       f"assets valid ({summary['success_rate']:.1f}% success rate) "
                       f"in {summary['scan_duration_seconds']:.1f}s")
            
            # Log trading activity
            logger.info(f"Initial asset scan completed - {summary['valid_assets_count']}/{summary['total_discovered']} valid")
            
            return result
            
        except Exception as e:
            logger.error(f"Error during initial scan: {e}")
            result.add_error("SCAN_ERROR", str(e))
            result.scan_duration = (utc_now() - scan_start).total_seconds()
            
            # Broadcast error to frontend
            error_message = {
                "type": "scanner_error",
                "payload": {
                    "status": "error",
                    "message": str(e),
                    "timestamp": utc_now().isoformat()
                }
            }
            await connection_manager.broadcast(error_message)
            
            return result
    
    async def _discover_markets(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Discover all available markets from the exchange."""
        try:
            return await self.market_api.get_usdt_markets(force_refresh)
        except Exception as e:
            logger.error(f"Failed to discover markets: {e}")
            raise
    
    def _extract_usdt_symbols(self, markets: List[Dict[str, Any]]) -> List[str]:
        """Extract USDT trading pair symbols from market data with validation."""
        symbols = []
        
        logger.info("Extracting all active USDT pairs...")
        
        for market in markets:
            try:
                symbol = market.get('symbol', '').strip()
                # We are interested in perpetual swap contracts ending in USDT
                if symbol.endswith('USDT') and market.get('active', False):
                    symbols.append(symbol)
            except Exception as e:
                logger.warning(f"Error processing market data for symbol '{market.get('symbol', 'N/A')}': {e}")
                continue
        
        logger.info(f"Found {len(symbols)} active USDT pairs.")

        # Sort to prioritize important assets
        priority_symbols = []
        other_symbols = []
        
        for symbol in symbols:
            if symbol in self.validator.criteria.PRIORITY_SYMBOLS:
                priority_symbols.append(symbol)
            else:
                other_symbols.append(symbol)
        
        # Return priority symbols first, then others
        return priority_symbols + sorted(other_symbols)
    
    async def _validate_discovered_assets(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Validate all discovered assets with incremental database saving."""
        logger.info(f"Starting incremental validation of {len(symbols)} assets...")
        
        try:
            # Use bulk validation with optimized database operations
            return await self._validate_and_collect_all_assets(symbols)
        except Exception as e:
            logger.error(f"Error during asset validation: {e}")
            return []
    
    async def _validate_and_collect_all_assets(self, symbols: List[str]) -> List[Tuple[str, Dict[str, Any]]]:
        """Validate assets with bulk database operations for maximum performance."""
        import asyncio
        from config.trading_config import TradingConfig
        
        # Sort symbols to prioritize important ones
        priority_symbols = [s for s in symbols if s in self.validator.criteria.PRIORITY_SYMBOLS]
        other_symbols = [s for s in symbols if s not in self.validator.criteria.PRIORITY_SYMBOLS]
        sorted_symbols = priority_symbols + other_symbols
        
        logger.info(f"Processing {len(sorted_symbols)} assets with bulk operations ({len(priority_symbols)} priority)")
        
        all_collected_results = []
        total_assets = len(sorted_symbols)
        processed_count = 0
        start_time = datetime.utcnow()
        
        # Configuração agressiva para pegar TODOS os ativos
        max_concurrent = 100  # Aumentar concorrência máxima
        
        for i in range(0, total_assets, max_concurrent):
            batch = sorted_symbols[i:i + max_concurrent]
            
            try:
                tasks = [self._validate_single_asset_optimized(symbol) for symbol in batch]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for j, result in enumerate(batch_results):
                    symbol = batch[j] 
                    processed_count += 1
                    
                    if isinstance(result, Exception):
                        logger.error(f"Error validating {symbol}: {result}")
                        validation_result = {
                            'symbol': symbol,
                            'is_valid': False,
                            'reason': f"Validation exception: {str(result)}",
                            'validation_timestamp': utc_now().isoformat(),
                            'validation_duration_seconds': 0
                        }
                        all_collected_results.append((symbol, validation_result))
                    else:
                        all_collected_results.append((symbol, result))
                
                # Calculate progress and ETA
                elapsed_time = (datetime.utcnow() - start_time).total_seconds()
                if processed_count > 0:
                    avg_time_per_asset = elapsed_time / processed_count
                    remaining_assets = total_assets - processed_count
                    estimated_remaining_time = avg_time_per_asset * remaining_assets
                    
                    # Broadcast progress to frontend
                    progress_message = {
                        "type": "scanner_progress",
                        "payload": {
                            "processed_count": processed_count,
                            "total_assets": total_assets,
                            "progress_percent": (processed_count / total_assets) * 100,
                            "estimated_remaining_time_seconds": estimated_remaining_time,
                            "elapsed_time_seconds": elapsed_time,
                            "status": "validating"
                        }
                    }
                    await connection_manager.broadcast(progress_message)
                
                # Progress logging
                if processed_count % 50 == 0 or processed_count == total_assets:
                    valid_count = sum(1 for r_sym, r_data in all_collected_results if r_data.get('is_valid', False))
                    logger.info(f"Progress: {processed_count}/{total_assets} assets processed "
                               f"({valid_count} valid, {processed_count - valid_count} invalid)")
                
                # Delay mínimo para não sobrecarregar a API
                if i + max_concurrent < total_assets:
                    # Delay fixo ultra agressivo de apenas 10ms entre batches
                    await asyncio.sleep(0.01)
                    
            except Exception as e:
                logger.error(f"Error processing batch {i//max_concurrent + 1}: {e}")
                continue
        
        # Log performance statistics
        cache_stats = self.cache.get_stats()
        rate_stats = self.rate_limiter.get_stats()
        
        logger.info(f"Bulk validation completed: {len(all_collected_results)} assets processed")
        logger.info(f"Cache performance: {cache_stats['hit_rate_percent']}% hit rate")
        logger.info(f"Rate limiting: {rate_stats.get('market_data', {}).get('utilization_percent', 0):.1f}% utilization")
        
        return all_collected_results
    
    async def _save_all_collected_results(self, all_collected_results: List[Tuple[str, Dict[str, Any]]]):
        """Save all collected validation results to database in a single transaction."""
        if not all_collected_results:
            return
            
        try:
            from utils.converters import convert_decimals
            
            bulk_update_data = []
            bulk_insert_data = []
            
            for symbol, validation_result in all_collected_results:
                is_valid = validation_result.get('is_valid', False)
                validation_data = convert_decimals(validation_result.get('data', {}))
                
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
                
                bulk_update_data.append({
                    'symbol': symbol,
                    'is_valid': is_valid,
                    'validation_data': db_validation_data
                })
                
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
            
            with get_session() as session:
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
                
                for insert_data in bulk_insert_data:
                    try:
                        existing = self.asset_repo.get_by_symbol(session, insert_data['symbol'])
                        if not existing:
                            self.asset_repo.create(session, **insert_data)
                    except Exception as insert_error:
                        logger.warning(f"Could not create asset {insert_data['symbol']}: {insert_error}")
                
                session.commit()
                
            logger.debug(f"Bulk saved {len(all_collected_results)} validation results to database")
            
        except Exception as e:
            logger.error(f"Failed to bulk save validation results: {e}")
            raise # Re-raise to indicate failure to the caller

    async def _validate_single_asset_optimized(self, symbol: str) -> Dict[str, Any]:
        """Validate a single asset with caching and optimized API calls."""
        try:
            # Check cache first
            cached_result = self.cache.get('validation', symbol)
            if cached_result:
                logger.debug(f"Using cached validation for {symbol}")
                return cached_result
            
            # Validate the asset using existing validator with rate limiting
            validation_result = await self.validator.validate_asset(symbol)
            
            # Cache the result for future use
            self.cache.set('validation', symbol, validation_result)
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Error in optimized validation for {symbol}: {e}")
            # Return a failed validation result
            return {
                'symbol': symbol,
                'is_valid': False,
                'reason': f"Processing error: {str(e)}",
                'validation_timestamp': utc_now().isoformat(),
                'validation_duration_seconds': 0
            }
    
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
    
    async def _process_validation_results(self, validation_results: Dict[str, Dict[str, Any]], 
                                        result: InitialScanResult):
        """Process validation results and populate scan result."""
        for symbol, validation_data in validation_results.items():
            try:
                if validation_data['is_valid']:
                    result.add_valid_asset(symbol, validation_data)
                else:
                    reason = validation_data.get('reason', 'Unknown validation failure')
                    result.add_invalid_asset(symbol, reason, validation_data)
                    
            except Exception as e:
                logger.error(f"Error processing validation result for {symbol}: {e}")
                result.add_error(symbol, str(e))
    
    
    
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
    
    async def _broadcast_progress(self, message: str, current_step: int, total_steps: int):
        """Broadcast scan progress to connected clients."""
        try:
            progress_percentage = int((current_step / total_steps) * 100)
            
            # Update global revalidation status if available
            try:
                # Import here to avoid circular import
                from api.web_api import revalidation_status
                if revalidation_status["running"]:
                    revalidation_status["progress"] = current_step
                    revalidation_status["total"] = total_steps
            except ImportError:
                # web_api not available, continue without updating
                pass
            
            progress_message = {
                "type": "scanner_progress",
                "payload": {
                    "message": message,
                    "current_step": current_step,
                    "total_steps": total_steps,
                    "progress_percentage": progress_percentage,
                    "timestamp": utc_now().isoformat()
                }
            }
            
            await connection_manager.broadcast(progress_message)
            logger.info(f"Scanner progress: {message} ({progress_percentage}%)")
            
        except Exception as e:
            logger.warning(f"Failed to broadcast progress update: {e}")


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