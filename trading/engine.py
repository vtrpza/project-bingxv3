# trading/engine.py
"""Core trading engine for BingX trading bot."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple

from database.models import Trade, Signal, Asset
from database.repository import TradeRepository, AssetRepository
from database.connection import get_session
from config.trading_config import TradingConfig
from api.client import BingXClient, TradingAPIError
from utils.logger import get_logger
from utils.validators import Validator, ValidationError

# Import test mode functions for aggressive testing
try:
    from api.web_api import is_test_mode_active, get_test_mode_config, increment_test_mode_stat
except ImportError:
    # Fallback functions if import fails
    def is_test_mode_active(): return False
    def get_test_mode_config(): return {}
    def increment_test_mode_stat(stat_name, increment=1): pass

logger = get_logger(__name__)


class TradingEngineError(Exception):
    """Base exception for trading engine errors."""
    pass


class InsufficientBalanceError(TradingEngineError):
    """Exception for insufficient balance errors."""
    pass


class TradingEngine:
    """
    Core trading engine responsible for:
    - Processing trading signals
    - Executing market orders
    - Managing position limits
    - Coordinating with risk management
    """
    
    def __init__(self, client: BingXClient, trade_repo: TradeRepository, asset_repo: AssetRepository):
        self.client = client
        self.trade_repo = trade_repo
        self.asset_repo = asset_repo
        self.config = TradingConfig
        
        # Trading state
        self._open_trades: Dict[str, Dict] = {}
        self._balance_cache: Dict[str, Decimal] = {}
        self._is_running = False
        
        # Trading limits
        self._max_concurrent_trades = self.config.MAX_CONCURRENT_TRADES
        self._max_position_size_percent = self.config.MAX_POSITION_SIZE_PERCENT
        self._min_order_size = self.config.MIN_ORDER_SIZE_USDT
        
        logger.info(f"TradingEngine initialized with max {self._max_concurrent_trades} concurrent trades")
    
    async def start(self):
        """Initialize and start the trading engine."""
        try:
            await self.client.initialize()
            await self._refresh_balance()
            await self._load_open_trades()
            self._is_running = True
            logger.info("TradingEngine started successfully")
        except Exception as e:
            logger.error(f"Failed to start TradingEngine: {e}")
            raise TradingEngineError(f"Engine startup failed: {e}")
    
    async def stop(self):
        """Stop the trading engine gracefully."""
        self._is_running = False
        logger.info("TradingEngine stopped")
    
    async def process_signal(self, signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process a trading signal and execute trade if conditions are met.
        
        Args:
            signal: Dictionary containing signal data
            
        Returns:
            Dictionary with trade result or None if not executed
        """
        if not self._is_running:
            logger.warning("TradingEngine not running, ignoring signal")
            return None
        
        try:
            # Validate signal
            validated_signal = await self._validate_signal(signal)
            if not validated_signal:
                return None
            
            # Check trading limits
            if not await self._check_trading_limits(validated_signal):
                return None
            
            # Calculate position size
            position_size = await self._calculate_position_size(
                validated_signal['symbol'], 
                validated_signal['current_price']
            )
            
            if not position_size:
                logger.warning(f"Could not calculate position size for {validated_signal['symbol']}")
                return None
            
            # Execute trade
            trade_result = await self._execute_trade(validated_signal, position_size)
            
            if trade_result:
                logger.info(f"✅ Trade executed: {trade_result['symbol']} {trade_result['side']} "
                          f"{trade_result['quantity']} @ {trade_result['entry_price']}")
            
            return trade_result
            
        except Exception as e:
            logger.error(f"Error processing signal: {e}")
            return None
    
    async def _validate_signal(self, signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Validate and enrich trading signal."""
        try:
            required_fields = ['symbol', 'signal_type', 'strength', 'rules_triggered', 'indicators_snapshot']
            for field in required_fields:
                if field not in signal:
                    logger.error(f"Missing required field in signal: {field}")
                    return None
            
            # Validate signal strength (with test mode adjustments)
            strength = Decimal(str(signal['strength']))
            threshold = self.config.SIGNAL_THRESHOLDS['buy']
            
            # In test mode, lower the threshold significantly to allow more trades
            if is_test_mode_active():
                test_config = get_test_mode_config()
                if test_config.get('aggressive_mode', False):
                    threshold = Decimal('0.1')  # Much lower threshold in test mode
                    logger.warning(f"🧪 TEST MODE: Using lowered signal threshold {threshold} for {signal['symbol']}")
            
            if strength < threshold:
                logger.debug(f"Signal strength too low: {strength} < {threshold}")
                return None
            
            # Validate signal type
            if signal['signal_type'] not in ['BUY', 'SELL']:
                logger.error(f"Invalid signal type: {signal['signal_type']}")
                return None
            
            # Get current price
            current_price = await self._get_current_price(signal['symbol'])
            if not current_price:
                logger.error(f"Could not get current price for {signal['symbol']}")
                return None
            
            # Validate asset
            from database.connection import get_session
            
            try:
                with get_session() as session:
                    asset = self.asset_repo.get_by_symbol(session, signal['symbol'])
                    if not asset or not asset.is_valid:
                        logger.warning(f"Asset not valid for trading: {signal['symbol']}")
                        return None
            except RuntimeError as e:
                logger.error(f"Database connection error: {e}")
                return None
            
            return {
                **signal,
                'current_price': current_price,
                'asset_id': asset.id,
                'timestamp': datetime.now(timezone.utc)
            }
            
        except Exception as e:
            logger.error(f"Error validating signal: {e}")
            return None
    
    async def _check_trading_limits(self, signal: Dict[str, Any]) -> bool:
        """Check if trading limits allow for new position (with test mode adjustments)."""
        try:
            # Check concurrent trades limit (with test mode override)
            open_trades_count = len(self._open_trades)
            max_trades = self._max_concurrent_trades
            
            # In test mode, temporarily increase the concurrent trades limit
            if is_test_mode_active():
                test_config = get_test_mode_config()
                test_max_trades = test_config.get('max_test_trades', 5)
                # Use the higher of current config or test config
                max_trades = max(max_trades, test_max_trades)
                logger.warning(f"🧪 TEST MODE: Using increased concurrent trades limit: {max_trades}")
            
            if open_trades_count >= max_trades:
                logger.warning(f"Max concurrent trades reached: {open_trades_count}/{max_trades}")
                return False
            
            # Check if already have position in this symbol
            symbol = signal['symbol']
            for trade_id, trade_data in self._open_trades.items():
                if trade_data['symbol'] == symbol:
                    logger.warning(f"Already have open trade for {symbol}")
                    return False
            
            # Check emergency stop
            if self.config.EMERGENCY_STOP:
                logger.warning("Emergency stop is active")
                return False
            
            # Check if trading is enabled
            if not self.config.TRADING_ENABLED:
                logger.warning("Trading is disabled")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking trading limits: {e}")
            return False
    
    async def _calculate_position_size(self, symbol: str, price: Decimal) -> Optional[Decimal]:
        """Calculate appropriate position size based on risk management."""
        try:
            # Get current balance
            usdt_balance = await self._get_usdt_balance()
            if not usdt_balance:
                logger.error("Could not get USDT balance")
                return None
            
            # Calculate max position value based on percentage
            max_position_value = usdt_balance * (self._max_position_size_percent / 100)
            
            # Calculate quantity
            quantity = max_position_value / price
            
            # Check minimum order size
            min_order_value = self._min_order_size
            min_quantity = min_order_value / price
            
            if quantity < min_quantity:
                logger.warning(f"Calculated quantity {quantity} below minimum {min_quantity}")
                return None
            
            # Round to appropriate precision
            quantity = self._round_quantity(symbol, quantity)
            
            logger.debug(f"Calculated position size for {symbol}: {quantity} (value: {quantity * price:.2f} USDT)")
            
            return quantity
            
        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return None
    
    async def _execute_trade(self, signal: Dict[str, Any], quantity: Decimal) -> Optional[Dict[str, Any]]:
        """Execute the actual trade on the exchange."""
        try:
            symbol = signal['symbol']
            side = signal['signal_type'].lower()  # 'BUY' -> 'buy'
            current_price = signal['current_price']
            
            # Calculate stop loss
            stop_loss_price = self._calculate_initial_stop_loss(current_price, side)
            
            # Create trade record first
            trade_data = {
                'asset_id': signal['asset_id'],
                'side': signal['signal_type'],
                'entry_price': current_price,
                'quantity': quantity,
                'stop_loss': stop_loss_price,
                'status': 'PENDING',
                'entry_reason': ', '.join(signal['rules_triggered']),
            }
            
            from database.connection import get_session
            
            with get_session() as session:
                trade = self.trade_repo.create_trade(
                    session=session,
                    asset_id=trade_data['asset_id'],
                    side=trade_data['side'],
                    entry_price=trade_data['entry_price'],
                    quantity=trade_data['quantity'],
                    stop_loss=trade_data['stop_loss'],
                    entry_reason=trade_data['entry_reason']
                )
                session.commit()
            
            trade_id = str(trade.id)
            
            try:
                # Execute market order
                order_result = await self.client.create_market_order(
                    symbol=symbol,
                    side=side,
                    amount=float(quantity)
                )
                
                # Update trade with execution details
                actual_price = Decimal(str(order_result.get('average', current_price)))
                actual_quantity = Decimal(str(order_result.get('amount', quantity)))
                
                with get_session() as session:
                    updated_trade = self.trade_repo.update(session, str(trade.id), 
                        entry_price=actual_price,
                        quantity=actual_quantity,
                        status='OPEN',
                        exchange_order_id=order_result.get('id')
                    )
                    session.commit()
                
                # Add to open trades tracking
                self._open_trades[trade_id] = {
                    'id': trade_id,
                    'symbol': symbol,
                    'side': signal['signal_type'],
                    'entry_price': actual_price,
                    'quantity': actual_quantity,
                    'stop_loss': stop_loss_price,
                    'entry_time': datetime.now(timezone.utc),
                    'signal_strength': signal['strength']
                }
                
                # Create stop loss order
                await self._create_stop_loss_order(trade_id, symbol, side, actual_quantity, stop_loss_price)
                
                # Update test mode statistics if active
                if is_test_mode_active():
                    increment_test_mode_stat('trades_executed')
                    logger.warning(f"🧪 TEST MODE: Trade executed for {symbol}, statistics updated")
                
                return {
                    'trade_id': trade_id,
                    'symbol': symbol,
                    'side': signal['signal_type'],
                    'entry_price': actual_price,
                    'quantity': actual_quantity,
                    'stop_loss': stop_loss_price,
                    'order_id': order_result.get('id'),
                    'timestamp': datetime.now(timezone.utc),
                    'test_mode': is_test_mode_active()
                }
                
            except TradingAPIError as e:
                # Update trade as failed
                with get_session() as session:
                    self.trade_repo.update(session, str(trade.id),
                        status='CANCELLED',
                        exit_reason=f'Order failed: {str(e)}'
                    )
                    session.commit()
                logger.error(f"Failed to execute order for trade {trade_id}: {e}")
                return None
                
        except Exception as e:
            logger.error(f"Error executing trade: {e}")
            return None
    
    def _calculate_initial_stop_loss(self, entry_price: Decimal, side: str) -> Decimal:
        """Calculate initial stop loss price (with test mode adjustments)."""
        stop_loss_percent = self.config.INITIAL_STOP_LOSS_PERCENT
        
        # In test mode, make stop loss more aggressive (tighter) to test more scenarios
        if is_test_mode_active():
            test_config = get_test_mode_config()
            if test_config.get('aggressive_mode', False):
                # Use a tighter stop loss (1% instead of 2%) to trigger more stop loss scenarios
                stop_loss_percent = Decimal('0.01')
                logger.warning(f"🧪 TEST MODE: Using aggressive stop loss {stop_loss_percent*100}% instead of {self.config.INITIAL_STOP_LOSS_PERCENT*100}%")
        
        if side.upper() == 'BUY':
            # For long positions, stop loss is below entry price
            return entry_price * (1 - stop_loss_percent)
        else:
            # For short positions, stop loss is above entry price
            return entry_price * (1 + stop_loss_percent)
    
    async def _create_stop_loss_order(self, trade_id: str, symbol: str, side: str, quantity: Decimal, stop_price: Decimal) -> Optional[str]:
        """Create stop loss order for the trade."""
        try:
            # Determine stop loss side (opposite of entry)
            stop_side = 'sell' if side.upper() == 'BUY' else 'buy'
            
            # Create stop loss order
            stop_order = await self.client.create_stop_loss_order(
                symbol=symbol,
                side=stop_side,
                amount=float(quantity),
                stop_price=float(stop_price)
            )
            
            if stop_order:
                logger.info(f"Stop loss order created for trade {trade_id}: {stop_order.get('id')}")
                return stop_order.get('id')
            
        except Exception as e:
            logger.error(f"Failed to create stop loss order for trade {trade_id}: {e}")
            return None
    
    async def _get_current_price(self, symbol: str) -> Optional[Decimal]:
        """Get current market price for symbol."""
        try:
            ticker = await self.client.fetch_ticker(symbol)
            return Decimal(str(ticker['last']))
        except Exception as e:
            logger.error(f"Error getting current price for {symbol}: {e}")
            return None
    
    async def _get_usdt_balance(self) -> Optional[Decimal]:
        """Get available USDT balance."""
        try:
            # Check cache first
            if 'USDT' in self._balance_cache:
                return self._balance_cache['USDT']
            
            balance = await self.client.fetch_balance()
            usdt_balance = Decimal(str(balance.get('USDT', {}).get('free', 0)))
            
            # Update cache
            self._balance_cache['USDT'] = usdt_balance
            
            return usdt_balance
            
        except Exception as e:
            logger.error(f"Error getting USDT balance: {e}")
            return None
    
    async def _refresh_balance(self):
        """Refresh balance cache."""
        try:
            balance = await self.client.fetch_balance()
            for currency, data in balance.items():
                if isinstance(data, dict) and 'free' in data:
                    self._balance_cache[currency] = Decimal(str(data['free']))
            
            logger.debug(f"Balance refreshed: {dict(self._balance_cache)}")
            
        except Exception as e:
            logger.error(f"Error refreshing balance: {e}")
    
    async def _load_open_trades(self):
        """Load open trades from database."""
        try:
            try:
                with get_session() as session:
                    open_trades = self.trade_repo.get_open_trades(session)
            except RuntimeError as e:
                logger.error(f"Database not initialized for loading trades: {e}")
                return
            
            for trade in open_trades:
                self._open_trades[str(trade.id)] = {
                    'id': str(trade.id),
                    'symbol': trade.asset.symbol,
                    'side': trade.side,
                    'entry_price': trade.entry_price,
                    'quantity': trade.quantity,
                    'stop_loss': trade.stop_loss,
                    'entry_time': trade.entry_time,
                    'signal_strength': None  # Not stored in trade
                }
            
            logger.info(f"Loaded {len(self._open_trades)} open trades from database")
            
        except Exception as e:
            logger.error(f"Error loading open trades: {e}")
    
    def _round_quantity(self, symbol: str, quantity: Decimal) -> Decimal:
        """Round quantity to appropriate precision for the symbol."""
        # Default to 6 decimal places for most crypto pairs
        return quantity.quantize(Decimal('0.000001'))
    
    async def get_open_trades(self) -> List[Dict[str, Any]]:
        """Get current open trades."""
        return list(self._open_trades.values())
    
    async def get_trading_stats(self) -> Dict[str, Any]:
        """Get trading engine statistics."""
        try:
            # Get balance
            usdt_balance = await self._get_usdt_balance()
            
            # Get trade counts
            try:
                with get_session() as session:
                    total_trades = self.trade_repo.get_trade_count(session)
            except RuntimeError:
                total_trades = 0
            open_trades_count = len(self._open_trades)
            
            return {
                'is_running': self._is_running,
                'open_trades': open_trades_count,
                'max_trades': self._max_concurrent_trades,
                'usdt_balance': float(usdt_balance) if usdt_balance else 0,
                'total_trades': total_trades,
                'trading_enabled': self.config.TRADING_ENABLED,
                'emergency_stop': self.config.EMERGENCY_STOP,
                'paper_trading': self.config.PAPER_TRADING
            }
            
        except Exception as e:
            logger.error(f"Error getting trading stats: {e}")
            return {}
    
    async def emergency_stop_all(self) -> bool:
        """Emergency stop - close all open positions."""
        try:
            logger.warning("🚨 EMERGENCY STOP - Closing all positions")
            
            closed_count = 0
            for trade_id, trade_data in self._open_trades.items():
                try:
                    # Close position at market
                    side = 'sell' if trade_data['side'] == 'BUY' else 'buy'
                    
                    await self.client.create_market_order(
                        symbol=trade_data['symbol'],
                        side=side,
                        amount=float(trade_data['quantity'])
                    )
                    
                    # Update trade as closed
                    with get_session() as session:
                        self.trade_repo.update(session, trade_id,
                            status='CLOSED',
                            exit_time=datetime.now(timezone.utc),
                            exit_reason='EMERGENCY_STOP'
                        )
                        session.commit()
                    
                    closed_count += 1
                    
                except Exception as e:
                    logger.error(f"Failed to close trade {trade_id}: {e}")
            
            # Clear open trades
            self._open_trades.clear()
            
            logger.warning(f"Emergency stop completed - {closed_count} positions closed")
            return True
            
        except Exception as e:
            logger.error(f"Error during emergency stop: {e}")
            return False