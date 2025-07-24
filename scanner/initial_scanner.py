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
            'added_timestamp': datetime.utcnow().isoformat()
        })
    
    def add_invalid_asset(self, symbol: str, reason: str, validation_data: Dict[str, Any] = None):
        """Add an invalid asset to results."""
        self.invalid_assets.append({
            'symbol': symbol,
            'reason': reason,
            'validation_data': validation_data or {},
            'rejected_timestamp': datetime.utcnow().isoformat()
        })
    
    def add_error(self, symbol: str, error: str):
        """Add an error encountered during scanning."""
        self.errors.append({
            'symbol': symbol,
            'error': error,
            'timestamp': datetime.utcnow().isoformat()
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
        
    async def scan_all_assets(self, force_refresh: bool = False, 
                            max_assets: Optional[int] = None) -> InitialScanResult:
        """Perform complete initial scan of all available assets."""
        logger.info("Starting initial asset scan...")
        scan_start = datetime.utcnow()
        result = InitialScanResult()
        result.scan_timestamp = scan_start.isoformat()
        
        try:
            # Step 1: Discover all available markets
            logger.info("Discovering available markets...")
            markets = await self._discover_markets(force_refresh)
            
            if not markets:
                logger.error("No markets discovered")
                return result
            
            # Step 2: Filter and limit markets
            usdt_symbols = self._extract_usdt_symbols(markets)
            
            if max_assets:
                usdt_symbols = usdt_symbols[:max_assets]
                logger.info(f"Limited scan to {len(usdt_symbols)} assets")
            
            result.total_discovered = len(usdt_symbols)
            logger.info(f"Discovered {result.total_discovered} USDT pairs for validation")
            
            # Step 3: Validate all discovered assets
            validation_results = await self._validate_discovered_assets(usdt_symbols)
            
            # Step 4: Process validation results
            await self._process_validation_results(validation_results, result)
            
            # Step 5: Results already persisted incrementally during validation
            # This step is now optional and used only for final summary logging
            logger.info("Results already persisted incrementally during validation process")
            
            # Calculate final metrics
            scan_end = datetime.utcnow()
            result.scan_duration = (scan_end - scan_start).total_seconds()
            
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
            result.scan_duration = (datetime.utcnow() - scan_start).total_seconds()
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
        
        # VST-ONLY CONFIGURATION - Only trade VST/USDT
        target_symbol = 'VST/USDT'
        
        # Debug: Log first 10 symbols to see what's available
        logger.info("Available symbols (first 10):")
        for i, market in enumerate(markets[:10]):
            logger.info(f"  {i+1}: {market.get('symbol', 'N/A')} (active: {market.get('active', False)})")
        
        # Look for VST variations
        vst_variations = ['VST/USDT', 'VST-USDT', 'VSTUSDT', 'vst/usdt', 'vst-usdt', 'vstusdt']
        
        for market in markets:
            try:
                symbol = market.get('symbol', '').strip()
                if symbol and market.get('active', False):
                    # Check for VST variations
                    for vst_var in vst_variations:
                        if symbol.upper() == vst_var.upper():
                            symbols.append(symbol)
                            logger.info(f"VST-only mode: Found VST symbol {symbol}")
                            return symbols  # Return immediately when found
            except Exception as e:
                logger.warning(f"Error processing market data: {e}")
                continue
        
        # If no VST found, log this
        logger.warning(f"VST symbol not found in {len(markets)} available markets")
        logger.info("Searching for symbols containing 'VST'...")
        
        # Search for any symbol containing VST
        for market in markets:
            symbol = market.get('symbol', '')
            if 'VST' in symbol.upper():
                logger.info(f"Found symbol containing VST: {symbol} (active: {market.get('active', False)})")
                if market.get('active', False):
                    symbols.append(symbol)
                    return symbols
        
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
            # Use incremental validation with immediate database saving
            return await self._validate_and_save_incremental(symbols)
        except Exception as e:
            logger.error(f"Error during asset validation: {e}")
            return {}
    
    async def _validate_and_save_incremental(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Validate assets incrementally, saving each result to database immediately."""
        import asyncio
        from config.trading_config import TradingConfig
        
        # Sort symbols to prioritize important ones
        priority_symbols = [s for s in symbols if s in self.validator.criteria.PRIORITY_SYMBOLS]
        other_symbols = [s for s in symbols if s not in self.validator.criteria.PRIORITY_SYMBOLS]
        sorted_symbols = priority_symbols + other_symbols
        
        logger.info(f"Processing {len(sorted_symbols)} assets incrementally ({len(priority_symbols)} priority)")
        
        # Process in batches to avoid overwhelming the API, but save each asset immediately
        results = {}
        max_concurrent = min(10, max(1, TradingConfig.MAX_ASSETS_TO_SCAN // 10))
        processed_count = 0
        
        for i in range(0, len(sorted_symbols), max_concurrent):
            batch = sorted_symbols[i:i + max_concurrent]
            
            try:
                # Create tasks for concurrent validation
                tasks = [self._validate_and_save_single_asset(symbol) for symbol in batch]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process results and update counters
                for j, result in enumerate(batch_results):
                    symbol = batch[j] 
                    processed_count += 1
                    
                    if isinstance(result, Exception):
                        logger.error(f"Error validating {symbol}: {result}")
                        # Create a failed validation result
                        validation_result = {
                            'symbol': symbol,
                            'is_valid': False,
                            'reason': f"Validation exception: {str(result)}",
                            'validation_timestamp': datetime.utcnow().isoformat(),
                            'validation_duration_seconds': 0
                        }
                        results[symbol] = validation_result
                        
                        # Try to save the failed result to database
                        try:
                            await self._save_validation_result_to_db(symbol, validation_result)
                        except Exception as save_error:
                            logger.error(f"Failed to save error result for {symbol}: {save_error}")
                    else:
                        results[symbol] = result
                
                # Progress logging every 25 assets
                if processed_count % 25 == 0 or processed_count == len(sorted_symbols):
                    valid_count = sum(1 for r in results.values() if r.get('is_valid', False))
                    logger.info(f"Progress: {processed_count}/{len(sorted_symbols)} assets processed "
                               f"({valid_count} valid, {processed_count - valid_count} invalid)")
                
                # Small delay between batches to be respectful to API
                if i + max_concurrent < len(sorted_symbols):
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"Error processing batch {i//max_concurrent + 1}: {e}")
                # Continue with next batch even if this one fails
                continue
        
        logger.info(f"Incremental validation completed: {len(results)} assets processed")
        return results
    
    async def _validate_and_save_single_asset(self, symbol: str) -> Dict[str, Any]:
        """Validate a single asset and immediately save result to database."""
        try:
            # Validate the asset using existing validator
            validation_result = await self.validator.validate_asset(symbol)
            
            # Save result to database immediately
            await self._save_validation_result_to_db(symbol, validation_result)
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Error in validate_and_save for {symbol}: {e}")
            # Return a failed validation result
            return {
                'symbol': symbol,
                'is_valid': False,
                'reason': f"Processing error: {str(e)}",
                'validation_timestamp': datetime.utcnow().isoformat(),
                'validation_duration_seconds': 0
            }
    
    async def _save_validation_result_to_db(self, symbol: str, validation_result: Dict[str, Any]):
        """Save a single validation result to database immediately."""
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
                            last_validation=datetime.utcnow(),
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
    
    async def _persist_scan_results(self, result: InitialScanResult):
        """Persist scan results to database with proper transaction handling."""
        # Import convert_decimals utility function
        from utils.converters import convert_decimals
        
        # Process valid assets in batches
        batch_size = 50
        valid_processed = 0
        
        for i in range(0, len(result.valid_assets), batch_size):
            batch = result.valid_assets[i:i + batch_size]
            
            try:
                with get_session() as session:
                    for asset_data in batch:
                        symbol = asset_data['symbol']
                        validation_data = asset_data['validation_data']
                        
                        try:
                            base_currency, quote_currency = symbol.split('/')
                            
                            # Extract and clean market data
                            market_summary = validation_data.get('data', {}).get('market_summary', {})
                            market_summary_clean = convert_decimals(market_summary)
                            validation_checks_clean = convert_decimals(validation_data.get('data', {}).get('validation_checks', {}))
                            
                            self.asset_repo.update_validation_status(
                                session,
                                symbol=symbol,
                                is_valid=True,
                                validation_data={
                                    'validation_timestamp': validation_data['validation_timestamp'],
                                    'validation_duration': validation_data['validation_duration_seconds'],
                                    'market_summary': market_summary_clean,
                                    'validation_checks': validation_checks_clean,
                                    'priority': validation_data.get('priority', False),
                                }
                            )
                            
                            # Create asset if it doesn't exist
                            existing_asset = self.asset_repo.get_by_symbol(session, symbol)
                            if not existing_asset:
                                min_order_size = market_summary.get('quote_volume_24h', TradingConfig.MIN_ORDER_SIZE_USDT)
                                if isinstance(min_order_size, (int, float, str)):
                                    min_order_size = min(float(min_order_size) / 1000, float(TradingConfig.MIN_ORDER_SIZE_USDT))
                                
                                self.asset_repo.create(
                                    session,
                                    symbol=symbol,
                                    base_currency=base_currency,
                                    quote_currency=quote_currency,
                                    is_valid=True,
                                    min_order_size=min_order_size,
                                    last_validation=datetime.utcnow(),
                                    validation_data=validation_data.get('data', {})
                                )
                            
                            valid_processed += 1
                            
                        except Exception as e:
                            logger.error(f"Error persisting valid asset {symbol}: {e}")
                            # Continue with next asset instead of failing the whole batch
                            continue
                            
            except Exception as e:
                logger.error(f"Error processing valid assets batch {i//batch_size + 1}: {e}")
                # Continue with next batch
                continue
        
        # Process invalid assets in batches
        invalid_processed = 0
        
        for i in range(0, len(result.invalid_assets), batch_size):
            batch = result.invalid_assets[i:i + batch_size]
            
            try:
                with get_session() as session:
                    for asset_data in batch:
                        symbol = asset_data['symbol']
                        
                        try:
                            validation_data_clean = convert_decimals(asset_data.get('validation_data', {}))
                            
                            self.asset_repo.update_validation_status(
                                session,
                                symbol=symbol,
                                is_valid=False,
                                validation_data={
                                    'rejection_reason': asset_data['reason'],
                                    'rejected_timestamp': asset_data['rejected_timestamp'],
                                    'validation_data': validation_data_clean,
                                }
                            )
                            
                            invalid_processed += 1
                            
                        except Exception as e:
                            logger.error(f"Error persisting invalid asset {symbol}: {e}")
                            # Continue with next asset
                            continue
                            
            except Exception as e:
                logger.error(f"Error processing invalid assets batch {i//batch_size + 1}: {e}")
                # Continue with next batch
                continue
        
        logger.info(f"Persisted scan results: {valid_processed}/{len(result.valid_assets)} valid, "
                   f"{invalid_processed}/{len(result.invalid_assets)} invalid assets")
    
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
                    'needs_refresh': (datetime.utcnow() - last_scan_time).total_seconds() > 86400,  # 24 hours
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