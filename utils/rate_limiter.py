# utils/rate_limiter.py
"""Intelligent rate limiter for BingX API calls."""

import asyncio
import time
import threading
from collections import defaultdict, deque
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from contextlib import asynccontextmanager
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RateLimit:
    """Rate limit configuration for an endpoint."""
    max_requests: int
    window_seconds: int
    adaptive_factor: float = 0.8  # Use 80% of available capacity


class IntelligentRateLimiter:
    """
    Intelligent rate limiter that adapts to BingX rate limits.
    
    BingX Rate Limits (2024):
    - Market interfaces: 100 requests per 10 seconds per IP
    - Account interfaces: 1000 requests per 10 seconds per IP
    """
    
    def __init__(self):
        # Rate limits per endpoint category - Optimized for maximum performance
        # Reduced safety factor to allow higher throughput
        self.limits = {
            'market_data': RateLimit(100, 10, 0.85),  # 85% of 100 req/10s = 8.5 req/s  
            'account': RateLimit(1000, 10, 0.90),     # 90% of 1000 req/10s = 90 req/s
        }
        
        # Track requests per category
        self.request_history: Dict[str, deque] = defaultdict(deque)
        self.last_cleanup = time.time()
        
        # Enhanced dynamic adjustment with performance metrics
        self.dynamic_delays: Dict[str, float] = defaultdict(float)
        self.consecutive_successes: Dict[str, int] = defaultdict(int)
        self.performance_metrics: Dict[str, Dict] = defaultdict(lambda: {
            'avg_response_time': 0.0,
            'success_rate': 1.0,
            'last_reset': time.time()
        })
        
        # Lock-free atomic operations counter
        self._request_counter = 0
        self._lock = threading.RLock()  # For thread-safe operations
        
    def _cleanup_old_requests(self, category: str, current_time: float):
        """Remove requests outside the time window."""
        if category not in self.request_history:
            return
            
        limit = self.limits[category]
        cutoff_time = current_time - limit.window_seconds
        
        history = self.request_history[category]
        while history and history[0] < cutoff_time:
            history.popleft()
    
    def _get_current_rate(self, category: str) -> float:
        """Get current request rate for category."""
        current_time = time.time()
        self._cleanup_old_requests(category, current_time)
        
        history = self.request_history[category]
        if len(history) < 2:
            return 0
            
        window_start = current_time - self.limits[category].window_seconds
        requests_in_window = len(history)
        
        return requests_in_window / self.limits[category].window_seconds
    
    def _calculate_wait_time(self, category: str) -> float:
        """Calculate optimal wait time before next request."""
        current_time = time.time()
        self._cleanup_old_requests(category, current_time)
        
        limit = self.limits[category]
        history = self.request_history[category]
        
        # Calculate effective rate limit (with safety factor)
        effective_limit = limit.max_requests * limit.adaptive_factor
        requests_in_window = len(history)
        
        # If we're under the limit, calculate optimal spacing
        if requests_in_window < effective_limit:
            # Calculate ideal rate: spread requests evenly across window
            ideal_interval = limit.window_seconds / effective_limit
            
            # Add dynamic delay if we've been getting rate limited
            dynamic_delay = self.dynamic_delays.get(category, 0)
            
            # Reduced minimum delay for better throughput
            return max(ideal_interval + dynamic_delay, 0.005)  # Min 5ms for faster processing
        
        # If we're at/over limit, wait until oldest request expires
        oldest_request = history[0]
        wait_time = limit.window_seconds - (current_time - oldest_request) + 0.1
        
        logger.warning(f"Rate limit approaching for {category}, waiting {wait_time:.2f}s")
        return max(wait_time, 0.1)
    
    async def acquire(self, category: str = 'market_data') -> None:
        """Acquire permission to make a request."""
        if category not in self.limits:
            logger.warning(f"Unknown rate limit category: {category}")
            category = 'market_data'
        
        wait_time = self._calculate_wait_time(category)
        
        if wait_time > 0.005:  # Only sleep if meaningful delay needed (reduced threshold)
            await asyncio.sleep(wait_time)
        
        # Record this request
        current_time = time.time()
        self.request_history[category].append(current_time)
    
    def record_success(self, category: str = 'market_data'):
        """Record successful request to adjust dynamic delays."""
        self.consecutive_successes[category] += 1
        
        # Reduce delay after consecutive successes (more aggressive reduction)
        if self.consecutive_successes[category] >= 3:  # Reduced from 5 to 3
            self.dynamic_delays[category] *= 0.8  # More aggressive reduction (0.8 vs 0.9)
            self.dynamic_delays[category] = max(0, self.dynamic_delays[category])
            self.consecutive_successes[category] = 0
    
    def record_rate_limit_hit(self, category: str = 'market_data'):
        """Record rate limit hit to increase delays."""
        self.consecutive_successes[category] = 0
        self.dynamic_delays[category] += 0.05  # Reduced penalty: Add 50ms delay (was 100ms)
        self.dynamic_delays[category] = min(0.5, self.dynamic_delays[category])  # Max 500ms (was 1s)
        
        logger.warning(f"Rate limit hit for {category}, increased delay to {self.dynamic_delays[category]:.2f}s")
    
    def get_stats(self) -> Dict[str, Dict]:
        """Get current rate limiter statistics."""
        stats = {}
        current_time = time.time()
        
        for category, limit in self.limits.items():
            self._cleanup_old_requests(category, current_time)
            history = self.request_history[category]
            
            current_rate = self._get_current_rate(category)
            effective_limit = limit.max_requests * limit.adaptive_factor
            
            stats[category] = {
                'requests_in_window': len(history),
                'max_requests': limit.max_requests,
                'effective_limit': effective_limit,
                'current_rate_per_sec': current_rate,
                'utilization_percent': (len(history) / effective_limit) * 100,
                'dynamic_delay': self.dynamic_delays.get(category, 0),
                'consecutive_successes': self.consecutive_successes.get(category, 0),
                'avg_response_time': self.performance_metrics[category]['avg_response_time'],
                'success_rate': self.performance_metrics[category]['success_rate'],
            }
        
        return stats


# Global rate limiter instance
_rate_limiter = None


def get_rate_limiter() -> IntelligentRateLimiter:
    """Get the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = IntelligentRateLimiter()
    return _rate_limiter


# Decorator for automatic rate limiting
def rate_limited(category: str = 'market_data'):
    """Decorator to automatically apply rate limiting to functions."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            limiter = get_rate_limiter()
            await limiter.acquire(category)
            
            try:
                result = await func(*args, **kwargs)
                limiter.record_success(category)
                return result
            except Exception as e:
                # Check if it's a rate limit error
                if "rate limit" in str(e).lower() or "too many requests" in str(e).lower():
                    limiter.record_rate_limit_hit(category)
                raise
        return wrapper
    return decorator