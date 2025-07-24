# trading/position_tracker.py
"""Position tracking and P&L monitoring system for BingX trading bot."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from database.models import Trade
from database.repository import TradeRepository
from database.connection import get_session
from config.trading_config import TradingConfig
from api.client import BingXClient
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PositionData:
    """Position data structure."""
    trade_id: str
    symbol: str
    side: str
    entry_price: Decimal
    current_price: Decimal
    quantity: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_percent: Decimal
    stop_loss: Optional[Decimal]
    take_profit: Optional[Decimal]
    entry_time: datetime
    duration: timedelta
    last_update: datetime


@dataclass
class PortfolioMetrics:
    """Portfolio-wide metrics."""
    total_positions: int
    total_unrealized_pnl: Decimal
    total_unrealized_pnl_percent: Decimal
    total_exposure: Decimal
    best_performer: Optional[PositionData]
    worst_performer: Optional[PositionData]
    avg_position_age: timedelta
    daily_pnl: Decimal
    weekly_pnl: Decimal
    monthly_pnl: Decimal


class PositionTrackerError(Exception):
    """Base exception for position tracker errors."""
    pass


class PositionTracker:
    """
    Position tracking system responsible for:
    - Monitoring open positions in real-time
    - Calculating unrealized P&L for all positions
    - Tracking position performance metrics
    - Providing portfolio-wide analytics
    - Detecting position-based alerts and triggers
    """
    
    def __init__(self, client: BingXClient, trade_repo: TradeRepository):
        self.client = client
        self.trade_repo = trade_repo
        self.config = TradingConfig
        
        # Position tracking
        self._positions: Dict[str, PositionData] = {}
        self._portfolio_metrics: Optional[PortfolioMetrics] = None
        
        # Price cache for efficiency
        self._price_cache: Dict[str, Dict] = {}  # symbol -> {price, timestamp}
        self._price_cache_ttl = 5  # seconds
        
        # Monitoring state
        self._is_running = False
        self._monitoring_task: Optional[asyncio.Task] = None
        self._update_interval = 5  # seconds
        
        # Performance tracking
        self._position_history: Dict[str, List[Dict]] = {}
        self._daily_snapshots: List[Dict] = []
        
        logger.info("PositionTracker initialized")
    
    async def start(self):
        """Start the position tracker and monitoring tasks."""
        try:
            self._is_running = True
            await self._load_positions()
            await self._calculate_initial_metrics()
            
            # Start position monitoring task
            self._monitoring_task = asyncio.create_task(self._monitor_positions())
            
            logger.info("PositionTracker started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start PositionTracker: {e}")
            raise PositionTrackerError(f"Position tracker startup failed: {e}")
    
    async def stop(self):
        """Stop the position tracker gracefully."""
        self._is_running = False
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        logger.info("PositionTracker stopped")
    
    async def add_position(self, trade: Trade) -> bool:
        """
        Add a new position to tracking.
        
        Args:
            trade: Trade object to track
            
        Returns:
            True if added successfully
        """
        try:
            trade_id = str(trade.id)
            
            # Get current price
            current_price = await self._get_current_price(trade.asset.symbol)
            if not current_price:
                logger.error(f"Could not get current price for {trade.asset.symbol}")
                return False
            
            # Calculate initial P&L
            unrealized_pnl = trade.calculate_pnl(current_price)
            unrealized_pnl_percent = self._calculate_pnl_percentage(
                trade.entry_price, current_price, trade.side
            )
            
            # Create position data
            position = PositionData(
                trade_id=trade_id,
                symbol=trade.asset.symbol,
                side=trade.side,
                entry_price=trade.entry_price,
                current_price=current_price,
                quantity=trade.quantity,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_percent=unrealized_pnl_percent,
                stop_loss=trade.stop_loss,
                take_profit=trade.take_profit,
                entry_time=trade.entry_time,
                duration=datetime.now(timezone.utc) - trade.entry_time,
                last_update=datetime.now(timezone.utc)
            )
            
            # Add to tracking
            self._positions[trade_id] = position
            
            # Initialize position history
            self._position_history[trade_id] = [{
                'timestamp': datetime.now(timezone.utc),
                'price': current_price,
                'pnl': unrealized_pnl,
                'pnl_percent': unrealized_pnl_percent
            }]
            
            logger.info(f"✅ Position added to tracking: {trade.asset.symbol} {trade.side} "
                       f"{trade.quantity} @ {trade.entry_price}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding position {trade.id}: {e}")
            return False
    
    async def remove_position(self, trade_id: uuid.UUID, exit_price: Optional[Decimal] = None) -> bool:
        """
        Remove a position from tracking (when trade is closed).
        
        Args:
            trade_id: Trade ID to remove
            exit_price: Final exit price if available
            
        Returns:
            True if removed successfully
        """
        try:
            trade_id_str = str(trade_id)
            
            if trade_id_str not in self._positions:
                logger.warning(f"Position {trade_id} not found in tracking")
                return False
            
            position = self._positions[trade_id_str]
            
            # Add final entry to history
            if exit_price:
                final_pnl = self._calculate_pnl(
                    position.entry_price, exit_price, position.side, position.quantity
                )
                final_pnl_percent = self._calculate_pnl_percentage(
                    position.entry_price, exit_price, position.side
                )
                
                self._position_history[trade_id_str].append({
                    'timestamp': datetime.now(timezone.utc),
                    'price': exit_price,
                    'pnl': final_pnl,
                    'pnl_percent': final_pnl_percent,
                    'final': True
                })
            
            # Remove from active tracking
            del self._positions[trade_id_str]
            
            logger.info(f"✅ Position removed from tracking: {position.symbol} "
                       f"(Final P&L: {position.unrealized_pnl:.2f})")
            
            return True
            
        except Exception as e:
            logger.error(f"Error removing position {trade_id}: {e}")
            return False
    
    async def update_position_price(self, trade_id: uuid.UUID, current_price: Decimal) -> Optional[PositionData]:
        """
        Update position with new price data.
        
        Args:
            trade_id: Trade ID to update
            current_price: New current price
            
        Returns:
            Updated position data or None if not found
        """
        try:
            trade_id_str = str(trade_id)
            
            if trade_id_str not in self._positions:
                return None
            
            position = self._positions[trade_id_str]
            
            # Update position data
            old_price = position.current_price
            position.current_price = current_price
            position.unrealized_pnl = self._calculate_pnl(
                position.entry_price, current_price, position.side, position.quantity
            )
            position.unrealized_pnl_percent = self._calculate_pnl_percentage(
                position.entry_price, current_price, position.side
            )
            position.duration = datetime.now(timezone.utc) - position.entry_time
            position.last_update = datetime.now(timezone.utc)
            
            # Add to history if price changed significantly
            if abs(current_price - old_price) > old_price * Decimal('0.001'):  # 0.1% change
                self._position_history[trade_id_str].append({
                    'timestamp': datetime.now(timezone.utc),
                    'price': current_price,
                    'pnl': position.unrealized_pnl,
                    'pnl_percent': position.unrealized_pnl_percent
                })
                
                # Keep history manageable
                if len(self._position_history[trade_id_str]) > 1000:
                    self._position_history[trade_id_str] = self._position_history[trade_id_str][-500:]
            
            return position
            
        except Exception as e:
            logger.error(f"Error updating position price for {trade_id}: {e}")
            return None
    
    async def update_stop_loss(self, trade_id: uuid.UUID, new_stop_loss: Decimal) -> bool:
        """
        Update stop loss for a position.
        
        Args:
            trade_id: Trade ID
            new_stop_loss: New stop loss price
            
        Returns:
            True if updated successfully
        """
        try:
            trade_id_str = str(trade_id)
            
            if trade_id_str not in self._positions:
                return False
            
            old_stop_loss = self._positions[trade_id_str].stop_loss
            self._positions[trade_id_str].stop_loss = new_stop_loss
            
            logger.debug(f"Stop loss updated for {trade_id}: {old_stop_loss} → {new_stop_loss}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating stop loss for {trade_id}: {e}")
            return False
    
    def _calculate_pnl(self, entry_price: Decimal, current_price: Decimal, side: str, quantity: Decimal) -> Decimal:
        """Calculate P&L in USDT."""
        price_diff = current_price - entry_price
        
        if side == 'SELL':
            price_diff = -price_diff
        
        return price_diff * quantity
    
    def _calculate_pnl_percentage(self, entry_price: Decimal, current_price: Decimal, side: str) -> Decimal:
        """Calculate P&L percentage."""
        if side == 'BUY':
            return (current_price - entry_price) / entry_price
        else:
            return (entry_price - current_price) / entry_price
    
    async def _monitor_positions(self):
        """Main position monitoring loop."""
        logger.info("Starting position monitoring")
        
        while self._is_running:
            try:
                # Update all positions
                await self._update_all_positions()
                
                # Calculate portfolio metrics
                await self._calculate_portfolio_metrics()
                
                # Check for alerts
                await self._check_position_alerts()
                
                # Log status periodically
                if datetime.now().minute % 10 == 0:  # Every 10 minutes
                    await self._log_portfolio_status()
                
                await asyncio.sleep(self._update_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in position monitoring: {e}")
                await asyncio.sleep(self._update_interval)
        
        logger.info("Position monitoring stopped")
    
    async def _update_all_positions(self):
        """Update all tracked positions with current prices."""
        try:
            # Get unique symbols
            symbols = list(set(pos.symbol for pos in self._positions.values()))
            
            # Update prices for all symbols
            price_updates = {}
            for symbol in symbols:
                current_price = await self._get_current_price(symbol)
                if current_price:
                    price_updates[symbol] = current_price
            
            # Update positions
            for trade_id, position in self._positions.items():
                if position.symbol in price_updates:
                    await self.update_position_price(
                        uuid.UUID(trade_id), 
                        price_updates[position.symbol]
                    )
            
        except Exception as e:
            logger.error(f"Error updating all positions: {e}")
    
    async def _calculate_portfolio_metrics(self):
        """Calculate portfolio-wide metrics."""
        try:
            if not self._positions:
                self._portfolio_metrics = None
                return
            
            positions = list(self._positions.values())
            
            # Basic metrics
            total_positions = len(positions)
            total_unrealized_pnl = sum(pos.unrealized_pnl for pos in positions)
            total_exposure = sum(pos.current_price * pos.quantity for pos in positions)
            
            # Calculate total unrealized P&L percentage
            total_investment = sum(pos.entry_price * pos.quantity for pos in positions)
            total_unrealized_pnl_percent = (
                total_unrealized_pnl / total_investment if total_investment > 0 else Decimal('0')
            )
            
            # Find best and worst performers
            best_performer = max(positions, key=lambda p: p.unrealized_pnl_percent, default=None)
            worst_performer = min(positions, key=lambda p: p.unrealized_pnl_percent, default=None)
            
            # Calculate average position age
            total_duration = sum((pos.duration.total_seconds() for pos in positions), 0)
            avg_position_age = timedelta(seconds=total_duration / total_positions) if total_positions > 0 else timedelta()
            
            # Calculate period P&L
            daily_pnl = await self._calculate_period_pnl(days=1)
            weekly_pnl = await self._calculate_period_pnl(days=7)
            monthly_pnl = await self._calculate_period_pnl(days=30)
            
            self._portfolio_metrics = PortfolioMetrics(
                total_positions=total_positions,
                total_unrealized_pnl=total_unrealized_pnl,
                total_unrealized_pnl_percent=total_unrealized_pnl_percent,
                total_exposure=total_exposure,
                best_performer=best_performer,
                worst_performer=worst_performer,
                avg_position_age=avg_position_age,
                daily_pnl=daily_pnl,
                weekly_pnl=weekly_pnl,
                monthly_pnl=monthly_pnl
            )
            
        except Exception as e:
            logger.error(f"Error calculating portfolio metrics: {e}")
    
    async def _calculate_period_pnl(self, days: int) -> Decimal:
        """Calculate P&L for a specific period."""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            period_trades = await self.trade_repo.get_trades_since(cutoff_date)
            
            total_pnl = Decimal('0')
            for trade in period_trades:
                if trade.status == 'CLOSED' and trade.pnl:
                    total_pnl += trade.pnl
                elif trade.status == 'OPEN' and str(trade.id) in self._positions:
                    # Add unrealized P&L for open positions
                    total_pnl += self._positions[str(trade.id)].unrealized_pnl
            
            return total_pnl
            
        except Exception as e:
            logger.error(f"Error calculating {days}-day P&L: {e}")
            return Decimal('0')
    
    async def _check_position_alerts(self):
        """Check for position-based alerts."""
        try:
            for position in self._positions.values():
                # Check for large unrealized losses
                if position.unrealized_pnl_percent < -0.05:  # -5%
                    logger.warning(f"🚨 Large unrealized loss: {position.symbol} "
                                 f"{position.unrealized_pnl_percent:.2%}")
                
                # Check for positions approaching stop loss
                if position.stop_loss:
                    distance_to_stop = abs(position.current_price - position.stop_loss) / position.current_price
                    if distance_to_stop < 0.02:  # Within 2% of stop loss
                        logger.warning(f"⚠️ Position near stop loss: {position.symbol} "
                                     f"(Distance: {distance_to_stop:.2%})")
                
                # Check for old positions
                if position.duration > timedelta(days=7):
                    logger.info(f"📅 Long-held position: {position.symbol} "
                               f"(Age: {position.duration.days} days)")
        
        except Exception as e:
            logger.error(f"Error checking position alerts: {e}")
    
    async def _get_current_price(self, symbol: str) -> Optional[Decimal]:
        """Get current price with caching."""
        try:
            # Check cache first
            if symbol in self._price_cache:
                cache_data = self._price_cache[symbol]
                cache_age = (datetime.now(timezone.utc) - cache_data['timestamp']).total_seconds()
                
                if cache_age < self._price_cache_ttl:
                    return cache_data['price']
            
            # Fetch new price
            ticker = await self.client.fetch_ticker(symbol)
            price = Decimal(str(ticker['last']))
            
            # Update cache
            self._price_cache[symbol] = {
                'price': price,
                'timestamp': datetime.now(timezone.utc)
            }
            
            return price
            
        except Exception as e:
            logger.error(f"Error getting current price for {symbol}: {e}")
            return None
    
    async def _log_portfolio_status(self):
        """Log current portfolio status."""
        try:
            if not self._portfolio_metrics:
                return
            
            metrics = self._portfolio_metrics
            
            logger.info(f"📊 Portfolio Status - Positions: {metrics.total_positions}, "
                       f"Unrealized P&L: {metrics.total_unrealized_pnl:.2f} USDT "
                       f"({metrics.total_unrealized_pnl_percent:.2%}), "
                       f"Daily P&L: {metrics.daily_pnl:.2f} USDT")
            
            if metrics.best_performer:
                logger.info(f"🏆 Best: {metrics.best_performer.symbol} "
                           f"{metrics.best_performer.unrealized_pnl_percent:.2%}")
            
            if metrics.worst_performer:
                logger.info(f"📉 Worst: {metrics.worst_performer.symbol} "
                           f"{metrics.worst_performer.unrealized_pnl_percent:.2%}")
        
        except Exception as e:
            logger.error(f"Error logging portfolio status: {e}")
    
    async def _load_positions(self):
        """Load open positions from database."""
        try:
            with get_session() as session:
                open_trades = self.trade_repo.get_open_trades(session)
            
            for trade in open_trades:
                await self.add_position(trade)
            
            logger.info(f"Loaded {len(self._positions)} positions from database")
            
        except Exception as e:
            logger.error(f"Error loading positions: {e}")
    
    async def _calculate_initial_metrics(self):
        """Calculate initial portfolio metrics."""
        await self._calculate_portfolio_metrics()
    
    # Public API methods
    
    async def get_all_positions(self) -> List[Dict[str, Any]]:
        """Get all tracked positions."""
        return [
            {
                'trade_id': pos.trade_id,
                'symbol': pos.symbol,
                'side': pos.side,
                'entry_price': float(pos.entry_price),
                'current_price': float(pos.current_price),
                'quantity': float(pos.quantity),
                'unrealized_pnl': float(pos.unrealized_pnl),
                'unrealized_pnl_percent': float(pos.unrealized_pnl_percent),
                'stop_loss': float(pos.stop_loss) if pos.stop_loss else None,
                'take_profit': float(pos.take_profit) if pos.take_profit else None,
                'entry_time': pos.entry_time.isoformat(),
                'duration_hours': pos.duration.total_seconds() / 3600,
                'last_update': pos.last_update.isoformat()
            }
            for pos in self._positions.values()
        ]
    
    async def get_position(self, trade_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Get specific position data."""
        trade_id_str = str(trade_id)
        
        if trade_id_str not in self._positions:
            return None
        
        pos = self._positions[trade_id_str]
        
        return {
            'trade_id': pos.trade_id,
            'symbol': pos.symbol,
            'side': pos.side,
            'entry_price': float(pos.entry_price),
            'current_price': float(pos.current_price),
            'quantity': float(pos.quantity),
            'unrealized_pnl': float(pos.unrealized_pnl),
            'unrealized_pnl_percent': float(pos.unrealized_pnl_percent),
            'stop_loss': float(pos.stop_loss) if pos.stop_loss else None,
            'take_profit': float(pos.take_profit) if pos.take_profit else None,
            'entry_time': pos.entry_time.isoformat(),
            'duration_hours': pos.duration.total_seconds() / 3600,
            'last_update': pos.last_update.isoformat()
        }
    
    async def get_portfolio_metrics(self) -> Optional[Dict[str, Any]]:
        """Get portfolio metrics."""
        if not self._portfolio_metrics:
            return None
        
        metrics = self._portfolio_metrics
        
        return {
            'total_positions': metrics.total_positions,
            'total_unrealized_pnl': float(metrics.total_unrealized_pnl),
            'total_unrealized_pnl_percent': float(metrics.total_unrealized_pnl_percent),
            'total_exposure': float(metrics.total_exposure),
            'best_performer': {
                'symbol': metrics.best_performer.symbol,
                'pnl_percent': float(metrics.best_performer.unrealized_pnl_percent)
            } if metrics.best_performer else None,
            'worst_performer': {
                'symbol': metrics.worst_performer.symbol,
                'pnl_percent': float(metrics.worst_performer.unrealized_pnl_percent)
            } if metrics.worst_performer else None,
            'avg_position_age_hours': metrics.avg_position_age.total_seconds() / 3600,
            'daily_pnl': float(metrics.daily_pnl),
            'weekly_pnl': float(metrics.weekly_pnl),
            'monthly_pnl': float(metrics.monthly_pnl)
        }
    
    async def get_position_history(self, trade_id: uuid.UUID, limit: int = 100) -> List[Dict[str, Any]]:
        """Get position price history."""
        trade_id_str = str(trade_id)
        
        if trade_id_str not in self._position_history:
            return []
        
        history = self._position_history[trade_id_str][-limit:]
        
        return [
            {
                'timestamp': entry['timestamp'].isoformat(),
                'price': float(entry['price']),
                'pnl': float(entry['pnl']),
                'pnl_percent': float(entry['pnl_percent']),
                'final': entry.get('final', False)
            }
            for entry in history
        ]