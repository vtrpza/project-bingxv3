# scanner/symbol_cache.py
"""In-memory cache for discovered symbols to improve scanner performance."""

import asyncio
import logging
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from utils.datetime_utils import utc_now
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SymbolData:
    """Container for symbol market data and metadata."""
    symbol: str
    is_valid: Optional[bool] = None
    last_updated: datetime = field(default_factory=utc_now)
    market_data: Dict = field(default_factory=dict)
    validation_data: Dict = field(default_factory=dict)
    
    def is_expired(self, ttl_seconds: int = 300) -> bool:
        """Check if cached data is expired."""
        return (utc_now() - self.last_updated).total_seconds() > ttl_seconds


class SymbolCache:
    """In-memory cache for trading symbols with TTL support."""
    
    def __init__(self, ttl_seconds: int = 300):
        """Initialize symbol cache.
        
        Args:
            ttl_seconds: Time-to-live for cached data (default: 5 minutes)
        """
        self._cache: Dict[str, SymbolData] = {}
        self._ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()
        logger.info(f"Symbol cache initialized with TTL={ttl_seconds}s")
    
    async def get(self, symbol: str) -> Optional[SymbolData]:
        """Get symbol data from cache if not expired."""
        async with self._lock:
            data = self._cache.get(symbol)
            if data and not data.is_expired(self._ttl_seconds):
                return data
            elif data:
                # Remove expired data
                del self._cache[symbol]
            return None
    
    async def set(self, symbol: str, data: SymbolData):
        """Store symbol data in cache."""
        async with self._lock:
            self._cache[symbol] = data
            logger.debug(f"Cached data for {symbol}")
    
    async def update(self, symbol: str, **kwargs):
        """Update existing symbol data."""
        async with self._lock:
            if symbol in self._cache:
                data = self._cache[symbol]
                for key, value in kwargs.items():
                    if hasattr(data, key):
                        setattr(data, key, value)
                data.last_updated = utc_now()
                logger.debug(f"Updated cache for {symbol}")
    
    async def get_all_symbols(self) -> List[str]:
        """Get all cached symbols (including expired)."""
        async with self._lock:
            return list(self._cache.keys())
    
    async def get_valid_symbols(self) -> List[str]:
        """Get all valid symbols from cache."""
        async with self._lock:
            valid_symbols = []
            for symbol, data in self._cache.items():
                if data.is_valid and not data.is_expired(self._ttl_seconds):
                    valid_symbols.append(symbol)
            return valid_symbols
    
    async def get_invalid_symbols(self) -> List[str]:
        """Get all invalid symbols from cache."""
        async with self._lock:
            invalid_symbols = []
            for symbol, data in self._cache.items():
                if data.is_valid is False and not data.is_expired(self._ttl_seconds):
                    invalid_symbols.append(symbol)
            return invalid_symbols
    
    async def clear(self):
        """Clear all cached data."""
        async with self._lock:
            self._cache.clear()
            logger.info("Symbol cache cleared")
    
    async def cleanup_expired(self):
        """Remove expired entries from cache."""
        async with self._lock:
            expired_symbols = []
            for symbol, data in list(self._cache.items()):
                if data.is_expired(self._ttl_seconds):
                    expired_symbols.append(symbol)
                    del self._cache[symbol]
            
            if expired_symbols:
                logger.info(f"Cleaned up {len(expired_symbols)} expired symbols from cache")
    
    async def bulk_update(self, symbols_data: Dict[str, SymbolData]):
        """Update multiple symbols at once."""
        async with self._lock:
            for symbol, data in symbols_data.items():
                self._cache[symbol] = data
            logger.info(f"Bulk updated {len(symbols_data)} symbols in cache")
    
    def get_stats(self) -> Dict:
        """Get cache statistics."""
        total = len(self._cache)
        valid_count = sum(1 for d in self._cache.values() if d.is_valid)
        invalid_count = sum(1 for d in self._cache.values() if d.is_valid is False)
        expired_count = sum(1 for d in self._cache.values() if d.is_expired(self._ttl_seconds))
        
        return {
            'total_symbols': total,
            'valid_symbols': valid_count,
            'invalid_symbols': invalid_count,
            'expired_entries': expired_count,
            'ttl_seconds': self._ttl_seconds
        }


# Global cache instance
_symbol_cache: Optional[SymbolCache] = None


def get_symbol_cache(ttl_seconds: int = 300) -> SymbolCache:
    """Get or create global symbol cache instance."""
    global _symbol_cache
    if _symbol_cache is None:
        _symbol_cache = SymbolCache(ttl_seconds)
    return _symbol_cache