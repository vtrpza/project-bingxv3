# trading/symbol_selector.py
"""
Autonomous symbol selector for trading system.
Selects symbols based on trading-specific criteria, independent of scanner.
"""

import asyncio
import logging
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from api.client import get_client
from api.market_data import get_market_data_api
from utils.logger import get_logger
from utils.datetime_utils import utc_now
from utils.rate_limiter import get_rate_limiter
from config.trading_config import TradingConfig

logger = get_logger(__name__)


@dataclass
class TradingSymbol:
    """Container for a symbol selected for trading."""
    symbol: str
    volume_24h: float
    spread_percent: float
    volatility_24h: float
    liquidity_score: float
    selection_score: float
    selection_reasons: List[str] = field(default_factory=list)
    selected_at: datetime = field(default_factory=utc_now)
    last_checked: datetime = field(default_factory=utc_now)
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'volume_24h': self.volume_24h,
            'spread_percent': self.spread_percent,
            'volatility_24h': self.volatility_24h,
            'liquidity_score': self.liquidity_score,
            'selection_score': self.selection_score,
            'selection_reasons': self.selection_reasons,
            'selected_at': self.selected_at.isoformat(),
            'last_checked': self.last_checked.isoformat()
        }


class SymbolSelector:
    """
    Selects symbols for trading based on specific criteria.
    Independent from the scanner system.
    """
    
    def __init__(self):
        self.client = get_client()
        self.market_api = get_market_data_api()
        self.rate_limiter = get_rate_limiter()
        
        # Selection criteria thresholds
        self.MIN_VOLUME_24H_USDT = 1_000_000  # $1M minimum daily volume
        self.MAX_SPREAD_PERCENT = 0.5  # 0.5% maximum spread
        self.MIN_VOLATILITY_24H = 0.5  # 0.5% minimum daily volatility
        self.MAX_VOLATILITY_24H = 20.0  # 20% maximum daily volatility
        self.MIN_LIQUIDITY_SCORE = 0.7  # Minimum liquidity score (0-1)
        
        # Maximum symbols to select for trading
        self.MAX_TRADING_SYMBOLS = 50
        
        logger.info(f"SymbolSelector initialized with criteria: "
                   f"Volume>${self.MIN_VOLUME_24H_USDT}, "
                   f"Spread<{self.MAX_SPREAD_PERCENT}%, "
                   f"Volatility {self.MIN_VOLATILITY_24H}-{self.MAX_VOLATILITY_24H}%")
    
    async def select_trading_symbols(self, force_refresh: bool = False) -> List[TradingSymbol]:
        """
        Select symbols for trading based on current market conditions.
        
        Returns:
            List of TradingSymbol objects that meet all criteria
        """
        try:
            logger.info("🎯 Starting trading symbol selection process...")
            
            # Step 1: Get all available USDT markets
            markets = await self._get_usdt_markets(force_refresh)
            logger.info(f"Found {len(markets)} USDT markets to evaluate")
            
            # Step 2: Evaluate each symbol
            selected_symbols = []
            evaluated_count = 0
            
            for market in markets:
                symbol = market.get('symbol', '')
                if not symbol or not symbol.endswith('USDT'):
                    continue
                
                evaluated_count += 1
                trading_symbol = await self._evaluate_symbol(symbol, market)
                
                if trading_symbol:
                    selected_symbols.append(trading_symbol)
                    logger.info(f"✅ Selected {symbol} for trading (score: {trading_symbol.selection_score:.2f})")
                
                # Rate limiting
                if evaluated_count % 10 == 0:
                    await asyncio.sleep(0.1)
            
            # Step 3: Sort by selection score and limit
            selected_symbols.sort(key=lambda x: x.selection_score, reverse=True)
            final_selection = selected_symbols[:self.MAX_TRADING_SYMBOLS]
            
            logger.info(f"🎯 Trading symbol selection complete: "
                       f"{len(final_selection)}/{evaluated_count} symbols selected")
            
            # Log selection summary
            self._log_selection_summary(final_selection)
            
            return final_selection
            
        except Exception as e:
            logger.error(f"Error in symbol selection: {e}")
            return []
    
    async def _get_usdt_markets(self, force_refresh: bool) -> List[Dict]:
        """Get all USDT trading pairs from exchange."""
        try:
            markets = await self.market_api.get_usdt_markets(force_refresh)
            # Filter active markets only
            return [m for m in markets if m.get('active', False)]
        except Exception as e:
            logger.error(f"Error fetching markets: {e}")
            return []
    
    async def _evaluate_symbol(self, symbol: str, market_data: Dict) -> Optional[TradingSymbol]:
        """
        Evaluate a single symbol against trading criteria.
        
        Returns:
            TradingSymbol if all criteria met, None otherwise
        """
        try:
            # Fetch current ticker data
            ticker = await self._fetch_ticker_safe(symbol)
            if not ticker:
                return None
            
            # Extract metrics
            volume_24h = float(ticker.get('quoteVolume', 0))  # Volume in USDT
            bid = float(ticker.get('bid', 0))
            ask = float(ticker.get('ask', 0))
            high_24h = float(ticker.get('high', 0))
            low_24h = float(ticker.get('low', 0))
            last_price = float(ticker.get('last', 0))
            
            # Skip if basic data is missing
            if not all([bid, ask, last_price, high_24h, low_24h]):
                return None
            
            # Calculate metrics
            spread_percent = ((ask - bid) / last_price) * 100 if last_price > 0 else float('inf')
            volatility_24h = ((high_24h - low_24h) / last_price) * 100 if last_price > 0 else 0
            
            # Calculate liquidity score (0-1)
            liquidity_score = self._calculate_liquidity_score(volume_24h, spread_percent)
            
            # Check criteria
            selection_reasons = []
            selection_score = 0.0
            
            # Volume check (weight: 30%)
            if volume_24h >= self.MIN_VOLUME_24H_USDT:
                selection_reasons.append(f"Volume: ${volume_24h:,.0f}")
                selection_score += 0.3 * min(volume_24h / (self.MIN_VOLUME_24H_USDT * 10), 1.0)
            else:
                return None  # Hard requirement
            
            # Spread check (weight: 25%)
            if spread_percent <= self.MAX_SPREAD_PERCENT:
                selection_reasons.append(f"Spread: {spread_percent:.3f}%")
                selection_score += 0.25 * (1 - spread_percent / self.MAX_SPREAD_PERCENT)
            else:
                return None  # Hard requirement
            
            # Volatility check (weight: 25%)
            if self.MIN_VOLATILITY_24H <= volatility_24h <= self.MAX_VOLATILITY_24H:
                selection_reasons.append(f"Volatility: {volatility_24h:.2f}%")
                # Prefer moderate volatility (peak at 5%)
                optimal_volatility = 5.0
                volatility_score = 1 - abs(volatility_24h - optimal_volatility) / optimal_volatility
                selection_score += 0.25 * max(0, volatility_score)
            else:
                return None  # Hard requirement
            
            # Liquidity check (weight: 20%)
            if liquidity_score >= self.MIN_LIQUIDITY_SCORE:
                selection_reasons.append(f"Liquidity: {liquidity_score:.2f}")
                selection_score += 0.2 * liquidity_score
            else:
                return None  # Hard requirement
            
            # Create trading symbol
            return TradingSymbol(
                symbol=symbol,
                volume_24h=volume_24h,
                spread_percent=spread_percent,
                volatility_24h=volatility_24h,
                liquidity_score=liquidity_score,
                selection_score=selection_score,
                selection_reasons=selection_reasons
            )
            
        except Exception as e:
            logger.debug(f"Error evaluating {symbol}: {e}")
            return None
    
    async def _fetch_ticker_safe(self, symbol: str) -> Optional[Dict]:
        """Fetch ticker with rate limiting and error handling."""
        try:
            await self.rate_limiter.acquire('market_data', weight=1)
            client = await self.client.get_client()
            return await client.fetch_ticker(symbol)
        except Exception as e:
            logger.debug(f"Error fetching ticker for {symbol}: {e}")
            return None
    
    def _calculate_liquidity_score(self, volume_24h: float, spread_percent: float) -> float:
        """
        Calculate liquidity score (0-1) based on volume and spread.
        Higher volume and lower spread = better liquidity.
        """
        # Volume score (0-1)
        volume_score = min(volume_24h / 10_000_000, 1.0)  # Max at $10M
        
        # Spread score (0-1) 
        spread_score = max(0, 1 - spread_percent / 1.0)  # 0% = 1.0, 1% = 0.0
        
        # Combined score (weighted average)
        liquidity_score = (volume_score * 0.7) + (spread_score * 0.3)
        
        return liquidity_score
    
    def _log_selection_summary(self, selected_symbols: List[TradingSymbol]):
        """Log summary of selected symbols."""
        if not selected_symbols:
            logger.warning("No symbols selected for trading")
            return
        
        logger.info("=" * 60)
        logger.info("TRADING SYMBOL SELECTION SUMMARY")
        logger.info("=" * 60)
        
        # Top 10 by score
        logger.info("\nTop 10 Selected Symbols:")
        for i, sym in enumerate(selected_symbols[:10], 1):
            logger.info(f"{i}. {sym.symbol} - Score: {sym.selection_score:.2f} - "
                       f"Volume: ${sym.volume_24h:,.0f} - "
                       f"Spread: {sym.spread_percent:.3f}% - "
                       f"Vol24h: {sym.volatility_24h:.2f}%")
        
        # Statistics
        avg_volume = sum(s.volume_24h for s in selected_symbols) / len(selected_symbols)
        avg_spread = sum(s.spread_percent for s in selected_symbols) / len(selected_symbols)
        avg_volatility = sum(s.volatility_24h for s in selected_symbols) / len(selected_symbols)
        
        logger.info(f"\nSelection Statistics:")
        logger.info(f"Total symbols selected: {len(selected_symbols)}")
        logger.info(f"Average 24h volume: ${avg_volume:,.0f}")
        logger.info(f"Average spread: {avg_spread:.3f}%")
        logger.info(f"Average 24h volatility: {avg_volatility:.2f}%")
        logger.info("=" * 60)


# Global instance
_symbol_selector: Optional[SymbolSelector] = None


def get_symbol_selector() -> SymbolSelector:
    """Get or create global symbol selector instance."""
    global _symbol_selector
    if _symbol_selector is None:
        _symbol_selector = SymbolSelector()
    return _symbol_selector