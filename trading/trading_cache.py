# trading/trading_cache.py
"""
Trading-specific cache for selected symbols and their data.
Independent from scanner cache.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from utils.datetime_utils import utc_now
from utils.logger import get_logger
from trading.symbol_selector import TradingSymbol

logger = get_logger(__name__)


@dataclass
class TradingSymbolData:
    """Extended data for a trading symbol including real-time metrics."""
    symbol: TradingSymbol
    last_price: float = 0.0
    current_signal: Optional[Dict] = None
    indicators_2h: Optional[Dict] = None
    indicators_4h: Optional[Dict] = None
    last_scanned: datetime = field(default_factory=utc_now)
    position_open: bool = False
    
    def is_stale(self, max_age_seconds: int = 30) -> bool:
        """Check if data is too old."""
        return (utc_now() - self.last_scanned).total_seconds() > max_age_seconds


class TradingCache:
    """
    Cache for trading-specific data.
    Stores only symbols selected for active trading.
    """
    
    def __init__(self, max_symbols: int = 50):
        self._symbols: Dict[str, TradingSymbolData] = {}
        self._selected_symbols: List[TradingSymbol] = []
        self._max_symbols = max_symbols
        self._lock = asyncio.Lock()
        self._last_selection_time: Optional[datetime] = None
        self._selection_ttl_minutes = 60  # Re-select symbols every hour
        
        logger.info(f"Trading cache initialized (max_symbols={max_symbols})")
    
    async def update_selected_symbols(self, symbols: List[TradingSymbol]):
        """Update the list of selected trading symbols."""
        async with self._lock:
            self._selected_symbols = symbols[:self._max_symbols]
            self._last_selection_time = utc_now()
            
            # Remove symbols no longer selected
            current_symbol_set = {s.symbol for s in symbols}
            to_remove = [sym for sym in self._symbols if sym not in current_symbol_set]
            for sym in to_remove:
                del self._symbols[sym]
                logger.debug(f"Removed {sym} from trading cache (no longer selected)")
            
            # Add new symbols
            for trading_symbol in self._selected_symbols:
                if trading_symbol.symbol not in self._symbols:
                    self._symbols[trading_symbol.symbol] = TradingSymbolData(symbol=trading_symbol)
                    logger.debug(f"Added {trading_symbol.symbol} to trading cache")
            
            logger.info(f"Trading cache updated with {len(self._selected_symbols)} selected symbols")
    
    async def get_selected_symbols(self) -> List[TradingSymbol]:
        """Get currently selected trading symbols."""
        async with self._lock:
            return self._selected_symbols.copy()
    
    async def get_trading_symbols(self) -> List[str]:
        """Get list of symbol names currently being traded."""
        async with self._lock:
            return list(self._symbols.keys())
    
    async def needs_reselection(self) -> bool:
        """Check if symbols need to be re-selected."""
        if self._last_selection_time is None:
            return True
        
        age_minutes = (utc_now() - self._last_selection_time).total_seconds() / 60
        return age_minutes >= self._selection_ttl_minutes
    
    async def get_symbol_data(self, symbol: str) -> Optional[TradingSymbolData]:
        """Get trading data for a specific symbol."""
        async with self._lock:
            return self._symbols.get(symbol)
    
    async def update_symbol_data(self, symbol: str, **kwargs):
        """Update trading data for a symbol."""
        async with self._lock:
            if symbol in self._symbols:
                data = self._symbols[symbol]
                for key, value in kwargs.items():
                    if hasattr(data, key):
                        setattr(data, key, value)
                data.last_scanned = utc_now()
    
    async def set_signal(self, symbol: str, signal: Dict):
        """Set current signal for a symbol."""
        await self.update_symbol_data(symbol, current_signal=signal)
        logger.info(f"Signal set for {symbol}: {signal.get('type')} ({signal.get('rule')})")
    
    async def clear_signal(self, symbol: str):
        """Clear signal for a symbol."""
        await self.update_symbol_data(symbol, current_signal=None)
    
    async def set_position_open(self, symbol: str, is_open: bool):
        """Mark if symbol has open position."""
        await self.update_symbol_data(symbol, position_open=is_open)
    
    async def get_symbols_with_signals(self) -> List[Tuple[str, Dict]]:
        """Get all symbols that currently have signals."""
        async with self._lock:
            result = []
            for symbol, data in self._symbols.items():
                if data.current_signal:
                    result.append((symbol, data.current_signal))
            return result
    
    async def get_symbols_without_positions(self) -> List[str]:
        """Get symbols that don't have open positions."""
        async with self._lock:
            return [
                symbol for symbol, data in self._symbols.items()
                if not data.position_open
            ]
    
    async def get_cache_stats(self) -> Dict:
        """Get cache statistics."""
        async with self._lock:
            total_symbols = len(self._symbols)
            with_signals = sum(1 for d in self._symbols.values() if d.current_signal)
            with_positions = sum(1 for d in self._symbols.values() if d.position_open)
            stale_data = sum(1 for d in self._symbols.values() if d.is_stale())
            
            return {
                'total_symbols': total_symbols,
                'symbols_with_signals': with_signals,
                'symbols_with_positions': with_positions,
                'stale_data_count': stale_data,
                'last_selection_time': self._last_selection_time.isoformat() if self._last_selection_time else None,
                'selection_age_minutes': (
                    (utc_now() - self._last_selection_time).total_seconds() / 60
                    if self._last_selection_time else None
                )
            }
    
    async def cleanup_stale_data(self, max_age_seconds: int = 60):
        """Remove stale data from cache."""
        async with self._lock:
            stale_symbols = [
                symbol for symbol, data in self._symbols.items()
                if data.is_stale(max_age_seconds) and not data.position_open
            ]
            
            for symbol in stale_symbols:
                # Don't remove, just clear the data
                self._symbols[symbol].current_signal = None
                self._symbols[symbol].indicators_2h = None
                self._symbols[symbol].indicators_4h = None
                logger.debug(f"Cleared stale data for {symbol}")
    
    def get_summary(self) -> Dict:
        """Get synchronous summary for logging."""
        return {
            'selected_symbols': len(self._selected_symbols),
            'cached_symbols': len(self._symbols),
            'last_selection': self._last_selection_time.isoformat() if self._last_selection_time else 'Never'
        }


# Global instance
_trading_cache: Optional[TradingCache] = None


def get_trading_cache(max_symbols: int = 50) -> TradingCache:
    """Get or create global trading cache instance."""
    global _trading_cache
    if _trading_cache is None:
        _trading_cache = TradingCache(max_symbols)
    return _trading_cache