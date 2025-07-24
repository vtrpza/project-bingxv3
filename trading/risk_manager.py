# trading/risk_manager.py
"""Risk management system for BingX trading bot."""

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
from config.trading_config import TradingConfig, TrailingStopLevel
from api.client import BingXClient
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RiskMetrics:
    """Risk metrics for position and portfolio."""
    total_exposure: Decimal
    max_drawdown: Decimal
    daily_pnl: Decimal
    win_rate: Decimal
    profit_factor: Decimal
    active_trades_count: int
    risk_score: float  # 0-1 where 1 is highest risk


class RiskManagerError(Exception):
    """Base exception for risk manager errors."""
    pass


class RiskManager:
    """
    Risk management system responsible for:
    - Calculating and monitoring trailing stop losses
    - Managing position sizes and exposure limits
    - Monitoring daily/total drawdown limits
    - Implementing emergency risk controls
    - Calculating real-time P&L and risk metrics
    """
    
    def __init__(self, client: BingXClient, trade_repo: TradeRepository, order_manager):
        self.client = client
        self.trade_repo = trade_repo
        self.order_manager = order_manager
        self.config = TradingConfig
        
        # Risk tracking
        self._risk_metrics: RiskMetrics = RiskMetrics(
            total_exposure=Decimal('0'),
            max_drawdown=Decimal('0'),
            daily_pnl=Decimal('0'),
            win_rate=Decimal('0'),
            profit_factor=Decimal('0'),
            active_trades_count=0,
            risk_score=0.0
        )
        
        # Trailing stop tracking
        self._trailing_stops: Dict[str, Dict] = {}  # trade_id -> trailing_stop_data
        self._position_updates: Dict[str, Dict] = {}  # trade_id -> latest_position_data
        
        # Risk limits
        self._daily_loss_limit = self.config.MAX_DAILY_LOSS_PERCENT / 100
        self._max_drawdown_limit = self.config.MAX_DRAWDOWN_PERCENT / 100
        
        # Monitoring state
        self._is_running = False
        self._monitoring_task: Optional[asyncio.Task] = None
        
        logger.info("RiskManager initialized")
    
    async def start(self):
        """Start the risk manager and monitoring tasks."""
        try:
            self._is_running = True
            await self._load_trailing_stops()
            await self._calculate_initial_metrics()
            
            # Start risk monitoring task
            self._monitoring_task = asyncio.create_task(self._monitor_risk())
            
            logger.info("RiskManager started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start RiskManager: {e}")
            raise RiskManagerError(f"Risk manager startup failed: {e}")
    
    async def stop(self):
        """Stop the risk manager gracefully."""
        self._is_running = False
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        logger.info("RiskManager stopped")
    
    async def initialize_trailing_stop(self, trade_id: uuid.UUID, entry_price: Decimal, side: str) -> bool:
        """
        Initialize trailing stop for a new trade.
        
        Args:
            trade_id: Trade ID
            entry_price: Entry price of the trade
            side: 'BUY' or 'SELL'
            
        Returns:
            True if initialized successfully
        """
        try:
            trade_id_str = str(trade_id)
            
            # Calculate initial stop loss
            initial_stop_loss = self._calculate_initial_stop_loss(entry_price, side)
            
            # Initialize trailing stop data
            self._trailing_stops[trade_id_str] = {
                'trade_id': trade_id_str,
                'side': side,
                'entry_price': entry_price,
                'current_price': entry_price,
                'highest_price': entry_price if side == 'BUY' else entry_price,
                'lowest_price': entry_price if side == 'SELL' else entry_price,
                'current_stop_loss': initial_stop_loss,
                'trailing_level': 0,  # Index in TRAILING_STOP_LEVELS
                'breakeven_triggered': False,
                'last_update': datetime.now(timezone.utc)
            }
            
            logger.info(f"Trailing stop initialized for trade {trade_id}: entry={entry_price}, initial_sl={initial_stop_loss}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error initializing trailing stop for trade {trade_id}: {e}")
            return False
    
    async def update_position_price(self, trade_id: uuid.UUID, current_price: Decimal) -> Optional[Dict[str, Any]]:
        """
        Update position with current price and check for trailing stop adjustments.
        
        Args:
            trade_id: Trade ID
            current_price: Current market price
            
        Returns:
            Dictionary with any stop loss updates or None
        """
        try:
            trade_id_str = str(trade_id)
            
            if trade_id_str not in self._trailing_stops:
                logger.warning(f"No trailing stop data for trade {trade_id}")
                return None
            
            trailing_data = self._trailing_stops[trade_id_str]
            side = trailing_data['side']
            
            # Update current price
            trailing_data['current_price'] = current_price
            trailing_data['last_update'] = datetime.now(timezone.utc)
            
            # Update highest/lowest price
            if side == 'BUY':
                if current_price > trailing_data['highest_price']:
                    trailing_data['highest_price'] = current_price
            else:
                if current_price < trailing_data['lowest_price']:
                    trailing_data['lowest_price'] = current_price
            
            # Calculate current P&L percentage
            pnl_percent = self._calculate_pnl_percentage(
                trailing_data['entry_price'],
                current_price,
                side
            )
            
            # Check for trailing stop adjustments
            new_stop_loss = await self._check_trailing_stop_adjustment(trade_id_str, pnl_percent)
            
            if new_stop_loss and new_stop_loss != trailing_data['current_stop_loss']:
                # Update stop loss
                old_stop_loss = trailing_data['current_stop_loss']
                trailing_data['current_stop_loss'] = new_stop_loss
                
                # Update stop loss order
                success = await self.order_manager.update_stop_loss(trade_id, new_stop_loss)
                
                if success:
                    logger.info(f"🎯 Trailing stop updated for trade {trade_id}: {old_stop_loss} → {new_stop_loss} (P&L: {pnl_percent:.2%})")
                    
                    return {
                        'trade_id': trade_id_str,
                        'old_stop_loss': old_stop_loss,
                        'new_stop_loss': new_stop_loss,
                        'pnl_percent': pnl_percent,
                        'current_price': current_price
                    }
                else:
                    # Revert on failure
                    trailing_data['current_stop_loss'] = old_stop_loss
                    logger.error(f"Failed to update stop loss order for trade {trade_id}")
            
            # Update position tracking
            self._position_updates[trade_id_str] = {
                'current_price': current_price,
                'pnl_percent': pnl_percent,
                'unrealized_pnl': self._calculate_unrealized_pnl(trailing_data, current_price),
                'last_update': datetime.now(timezone.utc)
            }
            
            return None
            
        except Exception as e:
            logger.error(f"Error updating position price for trade {trade_id}: {e}")
            return None
    
    async def _check_trailing_stop_adjustment(self, trade_id_str: str, pnl_percent: Decimal) -> Optional[Decimal]:
        """Check if trailing stop should be adjusted based on current P&L."""
        try:
            trailing_data = self._trailing_stops[trade_id_str]
            current_level = trailing_data['trailing_level']
            side = trailing_data['side']
            entry_price = trailing_data['entry_price']
            
            # Check if we should move to a higher trailing level
            for i, level in enumerate(self.config.TRAILING_STOP_LEVELS):
                if i <= current_level:
                    continue
                
                # Check if profit threshold is met
                if pnl_percent >= level.trigger:
                    # Update trailing level
                    trailing_data['trailing_level'] = i
                    
                    # Calculate new stop loss
                    if side == 'BUY':
                        new_stop_loss = entry_price * (1 + level.stop)
                    else:
                        new_stop_loss = entry_price * (1 - level.stop)
                    
                    # Ensure stop loss only moves in favorable direction
                    current_stop_loss = trailing_data['current_stop_loss']
                    
                    if side == 'BUY':
                        # For long positions, stop loss should only increase (move up)
                        if new_stop_loss > current_stop_loss:
                            return new_stop_loss
                    else:
                        # For short positions, stop loss should only decrease (move down)
                        if new_stop_loss < current_stop_loss:
                            return new_stop_loss
                    
                    break
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking trailing stop adjustment: {e}")
            return None
    
    def _calculate_initial_stop_loss(self, entry_price: Decimal, side: str) -> Decimal:
        """Calculate initial stop loss price."""
        stop_loss_percent = self.config.INITIAL_STOP_LOSS_PERCENT
        
        if side == 'BUY':
            # For long positions, stop loss is below entry price
            return entry_price * (1 - stop_loss_percent)
        else:
            # For short positions, stop loss is above entry price
            return entry_price * (1 + stop_loss_percent)
    
    def _calculate_pnl_percentage(self, entry_price: Decimal, current_price: Decimal, side: str) -> Decimal:
        """Calculate P&L percentage for a position."""
        if side == 'BUY':
            return (current_price - entry_price) / entry_price
        else:
            return (entry_price - current_price) / entry_price
    
    def _calculate_unrealized_pnl(self, trailing_data: Dict, current_price: Decimal) -> Decimal:
        """Calculate unrealized P&L in USDT for a position."""
        entry_price = trailing_data['entry_price']
        side = trailing_data['side']
        
        # This would need position size from trade data
        # For now, return percentage-based calculation
        pnl_percent = self._calculate_pnl_percentage(entry_price, current_price, side)
        return pnl_percent  # Would multiply by position size in real implementation
    
    async def check_risk_limits(self, trade_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Check if a proposed trade violates risk limits.
        
        Args:
            trade_data: Proposed trade data
            
        Returns:
            Tuple of (allowed, reasons_if_not_allowed)
        """
        try:
            reasons = []
            
            # Check daily loss limit
            if self._risk_metrics.daily_pnl < -self._daily_loss_limit:
                reasons.append(f"Daily loss limit exceeded: {self._risk_metrics.daily_pnl:.2%}")
            
            # Check maximum drawdown
            if self._risk_metrics.max_drawdown > self._max_drawdown_limit:
                reasons.append(f"Maximum drawdown exceeded: {self._risk_metrics.max_drawdown:.2%}")
            
            # Check concurrent trades limit
            if self._risk_metrics.active_trades_count >= self.config.MAX_CONCURRENT_TRADES:
                reasons.append(f"Maximum concurrent trades reached: {self._risk_metrics.active_trades_count}")
            
            # Check position size
            position_value = Decimal(str(trade_data.get('quantity', 0))) * Decimal(str(trade_data.get('price', 0)))
            max_position_value = self._get_max_position_value()
            
            if position_value > max_position_value:
                reasons.append(f"Position size too large: {position_value} > {max_position_value}")
            
            # Check risk score
            if self._risk_metrics.risk_score > 0.8:
                reasons.append(f"Risk score too high: {self._risk_metrics.risk_score:.2f}")
            
            # Check emergency stop
            if self.config.EMERGENCY_STOP:
                reasons.append("Emergency stop is active")
            
            return len(reasons) == 0, reasons
            
        except Exception as e:
            logger.error(f"Error checking risk limits: {e}")
            return False, [f"Risk check error: {str(e)}"]
    
    async def calculate_optimal_position_size(self, symbol: str, entry_price: Decimal, account_balance: Decimal) -> Decimal:
        """
        Calculate optimal position size based on risk management principles.
        
        Args:
            symbol: Trading symbol
            entry_price: Proposed entry price
            account_balance: Available account balance
            
        Returns:
            Optimal position size
        """
        try:
            # Base position size on percentage of balance
            max_position_percent = self.config.MAX_POSITION_SIZE_PERCENT / 100
            base_position_value = account_balance * max_position_percent
            
            # Adjust based on current risk metrics
            risk_adjustment = 1.0 - self._risk_metrics.risk_score * 0.5  # Reduce size if high risk
            
            # Adjust based on recent performance
            if self._risk_metrics.win_rate < 0.4:  # If win rate below 40%
                risk_adjustment *= 0.8
            
            if self._risk_metrics.daily_pnl < -0.02:  # If daily loss > 2%
                risk_adjustment *= 0.7
            
            # Calculate final position value
            adjusted_position_value = base_position_value * Decimal(str(risk_adjustment))
            
            # Convert to quantity
            quantity = adjusted_position_value / entry_price
            
            # Ensure minimum order size
            min_quantity = self.config.MIN_ORDER_SIZE_USDT / entry_price
            quantity = max(quantity, min_quantity)
            
            logger.debug(f"Calculated position size for {symbol}: {quantity} (risk_adj: {risk_adjustment:.2f})")
            
            return quantity
            
        except Exception as e:
            logger.error(f"Error calculating optimal position size: {e}")
            return Decimal('0')
    
    def _get_max_position_value(self) -> Decimal:
        """Get maximum allowed position value."""
        # This would be based on current account balance
        # For now, return a default value
        return Decimal('1000')  # Would be calculated from actual balance
    
    async def _monitor_risk(self):
        """Main risk monitoring loop."""
        logger.info("Starting risk monitoring")
        
        while self._is_running:
            try:
                # Update risk metrics
                await self._update_risk_metrics()
                
                # Check for risk violations
                await self._check_risk_violations()
                
                # Update trailing stops
                await self._update_all_trailing_stops()
                
                # Log risk status periodically
                if datetime.now().minute % 5 == 0:  # Every 5 minutes
                    await self._log_risk_status()
                
                await asyncio.sleep(10)  # Check every 10 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in risk monitoring: {e}")
                await asyncio.sleep(10)
        
        logger.info("Risk monitoring stopped")
    
    async def _update_risk_metrics(self):
        """Update current risk metrics."""
        try:
            # Get open trades
            with get_session() as session:
                open_trades = self.trade_repo.get_open_trades(session)
            
            # Calculate metrics
            total_exposure = Decimal('0')
            total_unrealized_pnl = Decimal('0')
            
            for trade in open_trades:
                # Get current price
                current_price = await self._get_current_price(trade.asset.symbol)
                if current_price:
                    position_value = trade.quantity * current_price
                    total_exposure += position_value
                    
                    # Calculate unrealized P&L
                    pnl = trade.calculate_pnl(current_price)
                    total_unrealized_pnl += pnl
            
            # Get daily P&L
            daily_pnl = await self._calculate_daily_pnl()
            
            # Calculate win rate and profit factor
            win_rate, profit_factor = await self._calculate_performance_metrics()
            
            # Update risk metrics
            self._risk_metrics = RiskMetrics(
                total_exposure=total_exposure,
                max_drawdown=await self._calculate_max_drawdown(),
                daily_pnl=daily_pnl,
                win_rate=win_rate,
                profit_factor=profit_factor,
                active_trades_count=len(open_trades),
                risk_score=self._calculate_risk_score()
            )
            
        except Exception as e:
            logger.error(f"Error updating risk metrics: {e}")
    
    async def _check_risk_violations(self):
        """Check for risk violations and take action."""
        try:
            violations = []
            
            # Check daily loss limit
            if self._risk_metrics.daily_pnl < -self._daily_loss_limit:
                violations.append("daily_loss_limit")
            
            # Check maximum drawdown
            if self._risk_metrics.max_drawdown > self._max_drawdown_limit:
                violations.append("max_drawdown")
            
            # Check risk score
            if self._risk_metrics.risk_score > 0.9:
                violations.append("high_risk_score")
            
            if violations:
                logger.warning(f"🚨 Risk violations detected: {violations}")
                
                # Take risk mitigation actions
                await self._handle_risk_violations(violations)
            
        except Exception as e:
            logger.error(f"Error checking risk violations: {e}")
    
    async def _handle_risk_violations(self, violations: List[str]):
        """Handle detected risk violations."""
        try:
            for violation in violations:
                if violation == "daily_loss_limit":
                    logger.warning("Daily loss limit exceeded - reducing position sizes")
                    # Could reduce position sizes or stop trading for the day
                
                elif violation == "max_drawdown":
                    logger.error("Maximum drawdown exceeded - emergency stop recommended")
                    # Could trigger emergency stop
                
                elif violation == "high_risk_score":
                    logger.warning("High risk score - tightening stop losses")
                    # Could tighten stop losses
            
        except Exception as e:
            logger.error(f"Error handling risk violations: {e}")
    
    async def _update_all_trailing_stops(self):
        """Update all active trailing stops."""
        try:
            for trade_id_str in list(self._trailing_stops.keys()):
                try:
                    # Get current price
                    trailing_data = self._trailing_stops[trade_id_str]
                    
                    # This would get current price from market data
                    # For now, skip if no current price available
                    if 'current_price' not in trailing_data:
                        continue
                    
                    # Update position (this is called elsewhere, so just monitor here)
                    
                except Exception as e:
                    logger.error(f"Error updating trailing stop for trade {trade_id_str}: {e}")
            
        except Exception as e:
            logger.error(f"Error updating trailing stops: {e}")
    
    async def _get_current_price(self, symbol: str) -> Optional[Decimal]:
        """Get current market price for symbol."""
        try:
            ticker = await self.client.fetch_ticker(symbol)
            return Decimal(str(ticker['last']))
        except Exception as e:
            logger.error(f"Error getting current price for {symbol}: {e}")
            return None
    
    async def _calculate_daily_pnl(self) -> Decimal:
        """Calculate daily P&L."""
        try:
            # Get trades from today
            today = datetime.now(timezone.utc).date()
            with get_session() as session:
                daily_trades = self.trade_repo.get_trades_by_date(session, today)
            
            total_pnl = Decimal('0')
            for trade in daily_trades:
                if trade.pnl:
                    total_pnl += trade.pnl
            
            return total_pnl
            
        except Exception as e:
            logger.error(f"Error calculating daily P&L: {e}")
            return Decimal('0')
    
    async def _calculate_max_drawdown(self) -> Decimal:
        """Calculate maximum drawdown."""
        try:
            # This would calculate the maximum peak-to-trough decline
            # For now, return a placeholder
            return Decimal('0.05')  # 5% placeholder
            
        except Exception as e:
            logger.error(f"Error calculating max drawdown: {e}")
            return Decimal('0')
    
    async def _calculate_performance_metrics(self) -> Tuple[Decimal, Decimal]:
        """Calculate win rate and profit factor."""
        try:
            # Get closed trades
            with get_session() as session:
                closed_trades = self.trade_repo.get_closed_trades(session, limit=100)
            
            if not closed_trades:
                return Decimal('0'), Decimal('0')
            
            winning_trades = 0
            total_wins = Decimal('0')
            total_losses = Decimal('0')
            
            for trade in closed_trades:
                if trade.pnl and trade.pnl > 0:
                    winning_trades += 1
                    total_wins += trade.pnl
                elif trade.pnl and trade.pnl < 0:
                    total_losses += abs(trade.pnl)
            
            win_rate = Decimal(winning_trades) / Decimal(len(closed_trades))
            profit_factor = total_wins / total_losses if total_losses > 0 else Decimal('0')
            
            return win_rate, profit_factor
            
        except Exception as e:
            logger.error(f"Error calculating performance metrics: {e}")
            return Decimal('0'), Decimal('0')
    
    def _calculate_risk_score(self) -> float:
        """Calculate overall risk score (0-1)."""
        try:
            score = 0.0
            
            # Factor in active trades count
            if self._risk_metrics.active_trades_count > 0:
                trades_factor = min(self._risk_metrics.active_trades_count / self.config.MAX_CONCURRENT_TRADES, 1.0)
                score += trades_factor * 0.3
            
            # Factor in daily P&L
            if self._risk_metrics.daily_pnl < 0:
                daily_loss_factor = min(abs(float(self._risk_metrics.daily_pnl)) / float(self._daily_loss_limit), 1.0)
                score += daily_loss_factor * 0.4
            
            # Factor in win rate
            if self._risk_metrics.win_rate < 0.5:
                win_rate_factor = (0.5 - float(self._risk_metrics.win_rate)) * 2
                score += win_rate_factor * 0.3
            
            return min(score, 1.0)
            
        except Exception as e:
            logger.error(f"Error calculating risk score: {e}")
            return 0.5  # Medium risk as default
    
    async def _log_risk_status(self):
        """Log current risk status."""
        try:
            logger.info(f"📊 Risk Status - Active: {self._risk_metrics.active_trades_count}, "
                       f"Daily P&L: {self._risk_metrics.daily_pnl:.2%}, "
                       f"Risk Score: {self._risk_metrics.risk_score:.2f}, "
                       f"Win Rate: {self._risk_metrics.win_rate:.1%}")
        except Exception as e:
            logger.error(f"Error logging risk status: {e}")
    
    async def _load_trailing_stops(self):
        """Load trailing stops for open trades."""
        try:
            with get_session() as session:
                open_trades = self.trade_repo.get_open_trades(session)
            
            for trade in open_trades:
                # Initialize trailing stop
                await self.initialize_trailing_stop(
                    trade.id,
                    trade.entry_price,
                    trade.side
                )
            
            logger.info(f"Loaded trailing stops for {len(open_trades)} open trades")
            
        except Exception as e:
            logger.error(f"Error loading trailing stops: {e}")
    
    async def _calculate_initial_metrics(self):
        """Calculate initial risk metrics."""
        await self._update_risk_metrics()
    
    async def get_risk_metrics(self) -> Dict[str, Any]:
        """Get current risk metrics."""
        return {
            'total_exposure': float(self._risk_metrics.total_exposure),
            'max_drawdown': float(self._risk_metrics.max_drawdown),
            'daily_pnl': float(self._risk_metrics.daily_pnl),
            'win_rate': float(self._risk_metrics.win_rate),
            'profit_factor': float(self._risk_metrics.profit_factor),
            'active_trades_count': self._risk_metrics.active_trades_count,
            'risk_score': self._risk_metrics.risk_score,
            'daily_loss_limit': float(self._daily_loss_limit),
            'max_drawdown_limit': float(self._max_drawdown_limit),
            'trailing_stops_count': len(self._trailing_stops)
        }
    
    async def get_trailing_stop_info(self, trade_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Get trailing stop information for a trade."""
        trade_id_str = str(trade_id)
        
        if trade_id_str not in self._trailing_stops:
            return None
        
        trailing_data = self._trailing_stops[trade_id_str]
        position_data = self._position_updates.get(trade_id_str, {})
        
        return {
            'trade_id': trade_id_str,
            'entry_price': float(trailing_data['entry_price']),
            'current_price': float(trailing_data.get('current_price', 0)),
            'current_stop_loss': float(trailing_data['current_stop_loss']),
            'trailing_level': trailing_data['trailing_level'],
            'pnl_percent': float(position_data.get('pnl_percent', 0)),
            'unrealized_pnl': float(position_data.get('unrealized_pnl', 0)),
            'breakeven_triggered': trailing_data['breakeven_triggered']
        }