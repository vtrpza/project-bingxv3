# utils/smart_cache.py
"""Smart caching system for market data and indicators."""

import asyncio
import time
from typing import Dict, Any, Optional, Callable, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CacheEntry:
    """Cache entry with expiration and metadata."""
    data: Any
    created_at: float
    expires_at: float
    access_count: int = 0
    last_access: float = 0


class SmartCache:
    """
    Intelligent cache for market data and indicators.
    
    Features:
    - TTL-based expiration
    - LRU eviction when memory limit reached
    - Category-based cache policies
    - Performance metrics
    """
    
    def __init__(self, max_size: int = 10000):
        self.cache: Dict[str, CacheEntry] = {}
        self.max_size = max_size
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'total_requests': 0
        }
        
        # Performance-optimized cache policies with intelligent TTL
        self.policies = {
            'market_summary': {'ttl': 30, 'priority': 'high'},     # 30s - high frequency data
            'ticker': {'ttl': 5, 'priority': 'critical'},          # 5s - real-time data
            'candles': {'ttl': 120, 'priority': 'medium'},         # 2min - technical analysis data
            'volume_analysis': {'ttl': 45, 'priority': 'high'},    # 45s - volume patterns
            'indicators': {'ttl': 300, 'priority': 'medium'},      # 5min - calculated indicators
            'validation': {'ttl': 900, 'priority': 'low'},         # 15min - validation results
            'markets': {'ttl': 1800, 'priority': 'low'},           # 30min - market list (reduced for freshness)
            'user_data': {'ttl': 60, 'priority': 'high'},          # 1min - user-specific data
        }
        
        # Performance monitoring
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # Cleanup every 5 minutes
    
    def _make_key(self, category: str, identifier: str, **kwargs) -> str:
        """Generate cache key from parameters with optimized string operations."""
        if not kwargs:
            return f"{category}:{identifier}"
        
        # Pre-allocate list for better performance
        parts = [category, identifier]
        if kwargs:
            # Use list comprehension and join for better performance than string concatenation
            sorted_items = sorted(kwargs.items())
            params = "_".join(f"{k}={v}" for k, v in sorted_items)
            parts.append(params)
        
        return ":".join(parts)
    
    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if cache entry is expired."""
        return time.time() > entry.expires_at
    
    def _cleanup_expired(self):
        """Remove expired entries with optimized batch deletion."""
        current_time = time.time()
        
        # Use dict comprehension for single-pass cleanup (more efficient than building list then deleting)
        original_size = len(self.cache)
        self.cache = {
            key: entry for key, entry in self.cache.items()
            if current_time <= entry.expires_at
        }
        
        cleaned_count = original_size - len(self.cache)
        if cleaned_count > 0:
            logger.debug(f"Cleaned up {cleaned_count} expired cache entries")
    
    def _evict_lru(self, count: int = 1):
        """Evict least recently used entries."""
        if len(self.cache) <= count:
            return
            
        # Sort by last access time and remove oldest
        sorted_entries = sorted(
            self.cache.items(),
            key=lambda x: x[1].last_access
        )
        
        for i in range(min(count, len(sorted_entries))):
            key = sorted_entries[i][0]
            del self.cache[key]
            self.stats['evictions'] += 1
    
    def _ensure_space(self):
        """Ensure cache doesn't exceed size limit with automatic cleanup."""
        current_time = time.time()
        
        # Periodic cleanup based on time interval
        if current_time - self._last_cleanup > self._cleanup_interval:
            self._cleanup_expired()
            self._last_cleanup = current_time
        
        # If still over limit, evict LRU entries
        if len(self.cache) >= self.max_size:
            excess = len(self.cache) - self.max_size + 1
            self._evict_lru(excess)
    
    def get(self, category: str, identifier: str, **kwargs) -> Optional[Any]:
        """Get cached data if available and not expired."""
        self.stats['total_requests'] += 1
        key = self._make_key(category, identifier, **kwargs)
        
        if key not in self.cache:
            self.stats['misses'] += 1
            return None
        
        entry = self.cache[key]
        
        # Check expiration
        if self._is_expired(entry):
            del self.cache[key]
            self.stats['misses'] += 1
            return None
        
        # Update access statistics
        entry.access_count += 1
        entry.last_access = time.time()
        self.stats['hits'] += 1
        
        logger.debug(f"Cache HIT: {key}")
        return entry.data
    
    def set(self, category: str, identifier: str, data: Any, **kwargs):
        """Cache data with appropriate TTL."""
        key = self._make_key(category, identifier, **kwargs)
        
        # Get TTL for this category
        policy = self.policies.get(category, {'ttl': 60})
        ttl = policy['ttl']
        
        # Ensure we have space
        self._ensure_space()
        
        # Create cache entry
        current_time = time.time()
        entry = CacheEntry(
            data=data,
            created_at=current_time,
            expires_at=current_time + ttl,
            access_count=1,
            last_access=current_time
        )
        
        self.cache[key] = entry
        logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")
    
    async def get_or_fetch(self, category: str, identifier: str, 
                          fetch_func: Callable, **kwargs) -> Any:
        """Get from cache or fetch if not available."""
        # Try cache first
        cached_data = self.get(category, identifier, **kwargs)
        if cached_data is not None:
            return cached_data
        
        # Cache miss - fetch data
        try:
            if asyncio.iscoroutinefunction(fetch_func):
                data = await fetch_func()
            else:
                data = fetch_func()
            
            # Cache the result
            self.set(category, identifier, data, **kwargs)
            return data
            
        except Exception as e:
            logger.error(f"Error fetching data for cache key {category}:{identifier}: {e}")
            raise
    
    def invalidate(self, category: str, identifier: str = None, **kwargs):
        """Invalidate cache entries."""
        if identifier is None:
            # Invalidate entire category
            keys_to_remove = [
                key for key in self.cache.keys()
                if key.startswith(f"{category}:")
            ]
        else:
            key = self._make_key(category, identifier, **kwargs)
            keys_to_remove = [key] if key in self.cache else []
        
        for key in keys_to_remove:
            del self.cache[key]
            
        if keys_to_remove:
            logger.debug(f"Invalidated {len(keys_to_remove)} cache entries for {category}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        total_requests = self.stats['total_requests']
        hit_rate = (self.stats['hits'] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hit_rate_percent': round(hit_rate, 2),
            'hits': self.stats['hits'],
            'misses': self.stats['misses'],
            'evictions': self.stats['evictions'],
            'total_requests': total_requests,
            'categories': list(self.policies.keys()),
        }
    
    def clear(self):
        """Clear all cache entries."""
        self.cache.clear()
        logger.info("Cache cleared")


# Global cache instance
_smart_cache = None


def get_smart_cache() -> SmartCache:
    """Get the global smart cache instance."""
    global _smart_cache
    if _smart_cache is None:
        _smart_cache = SmartCache()
    return _smart_cache


# Decorator for automatic caching
def cached(category: str, identifier_key: str = None, ttl: int = None):
    """Decorator to automatically cache function results."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            cache = get_smart_cache()
            
            # Generate identifier
            if identifier_key and identifier_key in kwargs:
                identifier = str(kwargs[identifier_key])
            elif len(args) > 0:
                identifier = str(args[0])
            else:
                identifier = func.__name__
            
            # Custom TTL if provided
            if ttl:
                original_policy = cache.policies.get(category, {})
                cache.policies[category] = {**original_policy, 'ttl': ttl}
            
            # Use cache
            return await cache.get_or_fetch(
                category, identifier, 
                lambda: func(*args, **kwargs),
                **{k: v for k, v in kwargs.items() if k != identifier_key}
            )
        return wrapper
    return decorator