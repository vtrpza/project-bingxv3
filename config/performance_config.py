# config/performance_config.py
"""Performance optimization configuration for BingX scanner."""

import os
from decimal import Decimal
from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    market_data_max_per_second: int = 8      # 80% of BingX 10 req/s limit
    account_data_max_per_second: int = 80    # 80% of BingX 100 req/s limit
    adaptive_factor: float = 0.8             # Safety factor
    dynamic_adjustment: bool = True          # Enable dynamic adjustment
    backoff_multiplier: float = 1.5          # Backoff multiplier on rate limit hit


@dataclass 
class CachingConfig:
    """Caching configuration."""
    max_cache_size: int = 50000              # Maximum cache entries
    default_ttl_seconds: int = 60            # Default TTL
    
    # TTL per data type (seconds)
    ttl_market_summary: int = 30             # Market data TTL
    ttl_ticker: int = 15                     # Ticker data TTL
    ttl_candles: int = 60                    # OHLCV data TTL
    ttl_volume_analysis: int = 45            # Volume analysis TTL
    ttl_indicators: int = 120                # Technical indicators TTL
    ttl_validation: int = 300                # Validation results TTL
    ttl_markets: int = 1800                  # Market list TTL


@dataclass
class BatchConfig:
    """Batch processing configuration."""
    # Asset table validation
    asset_table_batch_size: int = 20        # Concurrent assets per batch
    asset_table_max_batches: int = 100      # Max batches to process
    
    # Initial scanner
    initial_scan_batch_size: int = 25       # Concurrent validations per batch
    initial_scan_bulk_save: bool = True     # Use bulk database operations
    
    # Worker scanner  
    worker_batch_size: int = 15             # Concurrent assets per scan cycle
    worker_enable_caching: bool = True      # Enable caching in worker
    
    # Database operations
    db_bulk_insert_size: int = 100          # Records per bulk insert
    db_connection_pool_size: int = 20       # Database connection pool size


class PerformanceConfig:
    """Main performance configuration class."""
    
    def __init__(self):
        # Load from environment variables with defaults
        self.rate_limiting = RateLimitConfig(
            market_data_max_per_second=int(os.getenv("RATE_LIMIT_MARKET_DATA_PER_SEC", "8")),
            account_data_max_per_second=int(os.getenv("RATE_LIMIT_ACCOUNT_DATA_PER_SEC", "80")),
            adaptive_factor=float(os.getenv("RATE_LIMIT_ADAPTIVE_FACTOR", "0.8")),
            dynamic_adjustment=os.getenv("RATE_LIMIT_DYNAMIC_ADJUSTMENT", "True").lower() == "true",
            backoff_multiplier=float(os.getenv("RATE_LIMIT_BACKOFF_MULTIPLIER", "1.5"))
        )
        
        self.caching = CachingConfig(
            max_cache_size=int(os.getenv("CACHE_MAX_SIZE", "50000")),
            default_ttl_seconds=int(os.getenv("CACHE_DEFAULT_TTL", "60")),
            ttl_market_summary=int(os.getenv("CACHE_TTL_MARKET_SUMMARY", "30")),
            ttl_ticker=int(os.getenv("CACHE_TTL_TICKER", "15")),
            ttl_candles=int(os.getenv("CACHE_TTL_CANDLES", "60")),
            ttl_volume_analysis=int(os.getenv("CACHE_TTL_VOLUME_ANALYSIS", "45")),
            ttl_indicators=int(os.getenv("CACHE_TTL_INDICATORS", "120")),
            ttl_validation=int(os.getenv("CACHE_TTL_VALIDATION", "300")),
            ttl_markets=int(os.getenv("CACHE_TTL_MARKETS", "1800"))
        )
        
        self.batching = BatchConfig(
            asset_table_batch_size=int(os.getenv("BATCH_ASSET_TABLE_SIZE", "20")),
            asset_table_max_batches=int(os.getenv("BATCH_ASSET_TABLE_MAX", "100")),
            initial_scan_batch_size=int(os.getenv("BATCH_INITIAL_SCAN_SIZE", "25")),
            initial_scan_bulk_save=os.getenv("BATCH_INITIAL_SCAN_BULK_SAVE", "True").lower() == "true",
            worker_batch_size=int(os.getenv("BATCH_WORKER_SIZE", "15")),
            worker_enable_caching=os.getenv("BATCH_WORKER_ENABLE_CACHING", "True").lower() == "true",
            db_bulk_insert_size=int(os.getenv("DB_BULK_INSERT_SIZE", "100")),
            db_connection_pool_size=int(os.getenv("DB_CONNECTION_POOL_SIZE", "20"))
        )
    
    def get_optimal_batch_size(self, total_items: int, operation_type: str = "default") -> int:
        """Calculate optimal batch size based on total items and operation type."""
        if operation_type == "asset_table":
            base_size = self.batching.asset_table_batch_size
        elif operation_type == "initial_scan":
            base_size = self.batching.initial_scan_batch_size
        elif operation_type == "worker":
            base_size = self.batching.worker_batch_size
        else:
            base_size = 20  # Default
        
        # Adjust based on total items
        if total_items < base_size:
            return total_items
        elif total_items > base_size * 10:
            return min(base_size * 2, 50)  # Increase for large datasets, cap at 50
        else:
            return base_size
    
    def get_adaptive_delay(self, utilization_percent: float, base_delay: float = 0.2) -> float:
        """Calculate adaptive delay based on current utilization."""
        if utilization_percent < 50:
            return base_delay * 0.5  # Aggressive
        elif utilization_percent < 70:
            return base_delay       # Normal
        elif utilization_percent < 85:
            return base_delay * 2   # Conservative
        else:
            return base_delay * 4   # Very conservative
    
    def get_cache_ttl(self, data_type: str) -> int:
        """Get appropriate cache TTL for data type."""
        ttl_map = {
            'market_summary': self.caching.ttl_market_summary,
            'ticker': self.caching.ttl_ticker,
            'candles': self.caching.ttl_candles,
            'volume_analysis': self.caching.ttl_volume_analysis,
            'indicators': self.caching.ttl_indicators,
            'validation': self.caching.ttl_validation,
            'markets': self.caching.ttl_markets,
        }
        
        return ttl_map.get(data_type, self.caching.default_ttl_seconds)
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get current performance configuration summary."""
        return {
            'rate_limiting': {
                'market_data_per_sec': self.rate_limiting.market_data_max_per_second,
                'account_data_per_sec': self.rate_limiting.account_data_max_per_second,
                'adaptive_enabled': self.rate_limiting.dynamic_adjustment,
                'safety_factor': self.rate_limiting.adaptive_factor
            },
            'caching': {
                'max_size': self.caching.max_cache_size,
                'default_ttl': self.caching.default_ttl_seconds,
                'specialized_ttls': {
                    'market_data': self.caching.ttl_market_summary,
                    'indicators': self.caching.ttl_indicators,
                    'validation': self.caching.ttl_validation
                }
            },
            'batching': {
                'asset_table_batch': self.batching.asset_table_batch_size,
                'initial_scan_batch': self.batching.initial_scan_batch_size,
                'worker_batch': self.batching.worker_batch_size,
                'bulk_operations_enabled': self.batching.initial_scan_bulk_save
            }
        }
    
    def validate_config(self) -> List[str]:
        """Validate performance configuration."""
        errors = []
        
        # Rate limiting validation
        if self.rate_limiting.market_data_max_per_second > 10:
            errors.append("Market data rate limit exceeds BingX limit (10 req/s)")
        
        if self.rate_limiting.account_data_max_per_second > 100:
            errors.append("Account data rate limit exceeds BingX limit (100 req/s)")
        
        # Caching validation
        if self.caching.max_cache_size < 1000:
            errors.append("Cache size too small (minimum 1000 entries recommended)")
        
        if self.caching.default_ttl_seconds < 10:
            errors.append("Default TTL too low (minimum 10 seconds recommended)")
        
        # Batching validation
        if self.batching.asset_table_batch_size > 50:
            errors.append("Asset table batch size too large (maximum 50 recommended)")
        
        if self.batching.worker_batch_size > 30:
            errors.append("Worker batch size too large (maximum 30 recommended)")
        
        return errors


# Global performance configuration instance
_performance_config = None


def get_performance_config() -> PerformanceConfig:
    """Get the global performance configuration instance."""
    global _performance_config
    if _performance_config is None:
        _performance_config = PerformanceConfig()
    return _performance_config


def validate_performance_config() -> bool:
    """Validate the current performance configuration."""
    config = get_performance_config()
    errors = config.validate_config()
    
    if errors:
        from utils.logger import get_logger
        logger = get_logger(__name__)
        logger.error("Performance configuration validation failed:")
        for error in errors:
            logger.error(f"  - {error}")
        return False
    
    return True