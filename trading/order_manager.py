# trading/order_manager.py
"""Order management system for BingX trading bot."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

from database.models import Order, Trade
from database.repository import OrderRepository, TradeRepository
from config.trading_config import TradingConfig
from api.client import BingXClient, TradingAPIError
from utils.logger import get_logger
from utils.validators import Validator, ValidationError

logger = get_logger(__name__)


class OrderType(Enum):
    """Order types supported by the system."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"


class OrderStatus(Enum):
    """Order status enumeration."""
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class OrderManagerError(Exception):
    """Base exception for order manager errors."""
    pass


class OrderManager:
    """
    Order management system responsible for:
    - Creating and submitting orders to exchange
    - Monitoring order status and updates
    - Managing order lifecycle
    - Handling order-related errors and retries
    """
    
    def __init__(self, client: BingXClient, order_repo: OrderRepository, trade_repo: TradeRepository):
        self.client = client
        self.order_repo = order_repo
        self.trade_repo = trade_repo
        self.config = TradingConfig
        
        # Order tracking
        self._active_orders: Dict[str, Dict] = {}
        self._order_callbacks: Dict[str, List] = {}
        self._monitoring_task: Optional[asyncio.Task] = None
        self._is_running = False
        
        # Configuration
        self._order_timeout = self.config.ORDER_TIMEOUT_SECONDS
        self._retry_attempts = self.config.ORDER_RETRY_ATTEMPTS
        self._retry_delay = self.config.ORDER_RETRY_DELAY
        
        logger.info("OrderManager initialized")
    
    async def start(self):
        """Start the order manager and monitoring tasks."""
        try:
            self._is_running = True
            await self._load_active_orders()
            
            # Start order monitoring task
            self._monitoring_task = asyncio.create_task(self._monitor_orders())
            
            logger.info("OrderManager started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start OrderManager: {e}")
            raise OrderManagerError(f"Manager startup failed: {e}")
    
    async def stop(self):
        """Stop the order manager gracefully."""
        self._is_running = False
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        logger.info("OrderManager stopped")
    
    async def create_market_order(
        self, 
        trade_id: uuid.UUID, 
        symbol: str, 
        side: str, 
        quantity: Decimal,
        callback: Optional[callable] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create and submit a market order.
        
        Args:
            trade_id: Associated trade ID
            symbol: Trading pair symbol
            side: 'buy' or 'sell'
            quantity: Order quantity
            callback: Optional callback function for order updates
            
        Returns:
            Order result dictionary or None if failed
        """
        try:
            # Create order record
            order_data = {
                'trade_id': trade_id,
                'type': OrderType.MARKET.value,
                'side': side.upper(),
                'quantity': quantity,
                'status': OrderStatus.PENDING.value
            }
            
            order = await self.order_repo.create_order(order_data)
            order_id = str(order.id)
            
            # Add to active orders
            self._active_orders[order_id] = {
                'id': order_id,
                'trade_id': str(trade_id),
                'symbol': symbol,
                'type': OrderType.MARKET.value,
                'side': side,
                'quantity': quantity,
                'status': OrderStatus.PENDING.value,
                'created_at': datetime.now(timezone.utc),
                'attempts': 0
            }
            
            # Add callback if provided
            if callback:
                if order_id not in self._order_callbacks:
                    self._order_callbacks[order_id] = []
                self._order_callbacks[order_id].append(callback)
            
            # Submit order to exchange
            result = await self._submit_market_order(order_id, symbol, side, quantity)
            
            if result:
                logger.info(f"✅ Market order created: {symbol} {side} {quantity} @ {result.get('price', 'market')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error creating market order: {e}")
            return None
    
    async def create_stop_loss_order(
        self,
        trade_id: uuid.UUID,
        symbol: str,
        side: str,
        quantity: Decimal,
        stop_price: Decimal,
        callback: Optional[callable] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create and submit a stop loss order.
        
        Args:
            trade_id: Associated trade ID
            symbol: Trading pair symbol
            side: 'buy' or 'sell'
            quantity: Order quantity
            stop_price: Stop trigger price
            callback: Optional callback function for order updates
            
        Returns:
            Order result dictionary or None if failed
        """
        try:
            # Create order record
            order_data = {
                'trade_id': trade_id,
                'type': OrderType.STOP_LOSS.value,
                'side': side.upper(),
                'price': stop_price,
                'quantity': quantity,
                'status': OrderStatus.PENDING.value
            }
            
            order = await self.order_repo.create_order(order_data)
            order_id = str(order.id)
            
            # Add to active orders
            self._active_orders[order_id] = {
                'id': order_id,
                'trade_id': str(trade_id),
                'symbol': symbol,
                'type': OrderType.STOP_LOSS.value,
                'side': side,
                'quantity': quantity,
                'stop_price': stop_price,
                'status': OrderStatus.PENDING.value,
                'created_at': datetime.now(timezone.utc),
                'attempts': 0
            }
            
            # Add callback if provided
            if callback:
                if order_id not in self._order_callbacks:
                    self._order_callbacks[order_id] = []
                self._order_callbacks[order_id].append(callback)
            
            # Submit order to exchange
            result = await self._submit_stop_loss_order(order_id, symbol, side, quantity, stop_price)
            
            if result:
                logger.info(f"✅ Stop loss order created: {symbol} {side} {quantity} @ {stop_price}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error creating stop loss order: {e}")
            return None
    
    async def create_take_profit_order(
        self,
        trade_id: uuid.UUID,
        symbol: str,
        side: str,
        quantity: Decimal,
        target_price: Decimal,
        callback: Optional[callable] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create and submit a take profit (limit) order.
        
        Args:
            trade_id: Associated trade ID
            symbol: Trading pair symbol
            side: 'buy' or 'sell'
            quantity: Order quantity
            target_price: Target limit price
            callback: Optional callback function for order updates
            
        Returns:
            Order result dictionary or None if failed
        """
        try:
            # Create order record
            order_data = {
                'trade_id': trade_id,
                'type': OrderType.TAKE_PROFIT.value,
                'side': side.upper(),
                'price': target_price,
                'quantity': quantity,
                'status': OrderStatus.PENDING.value
            }
            
            order = await self.order_repo.create_order(order_data)
            order_id = str(order.id)
            
            # Add to active orders
            self._active_orders[order_id] = {
                'id': order_id,
                'trade_id': str(trade_id),
                'symbol': symbol,
                'type': OrderType.TAKE_PROFIT.value,
                'side': side,
                'quantity': quantity,
                'target_price': target_price,
                'status': OrderStatus.PENDING.value,
                'created_at': datetime.now(timezone.utc),
                'attempts': 0
            }
            
            # Add callback if provided
            if callback:
                if order_id not in self._order_callbacks:
                    self._order_callbacks[order_id] = []
                self._order_callbacks[order_id].append(callback)
            
            # Submit order to exchange
            result = await self._submit_limit_order(order_id, symbol, side, quantity, target_price)
            
            if result:
                logger.info(f"✅ Take profit order created: {symbol} {side} {quantity} @ {target_price}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error creating take profit order: {e}")
            return None
    
    async def cancel_order(self, order_id: str, reason: str = "Manual cancellation") -> bool:
        """
        Cancel an active order.
        
        Args:
            order_id: Internal order ID
            reason: Cancellation reason
            
        Returns:
            True if cancelled successfully, False otherwise
        """
        try:
            if order_id not in self._active_orders:
                logger.warning(f"Order {order_id} not found in active orders")
                return False
            
            order_data = self._active_orders[order_id]
            exchange_order_id = order_data.get('exchange_order_id')
            
            if not exchange_order_id:
                logger.warning(f"No exchange order ID for order {order_id}")
                return False
            
            # Cancel on exchange
            try:
                await self.client.cancel_order(exchange_order_id, order_data['symbol'])
                
                # Update order status
                await self._update_order_status(order_id, OrderStatus.CANCELLED.value, {
                    'cancelled_reason': reason,
                    'cancelled_at': datetime.now(timezone.utc)
                })
                
                logger.info(f"✅ Order cancelled: {order_id} - {reason}")
                return True
                
            except TradingAPIError as e:
                if "Order not found" in str(e):
                    # Order might already be filled or cancelled
                    logger.warning(f"Order {order_id} not found on exchange, marking as cancelled")
                    await self._update_order_status(order_id, OrderStatus.CANCELLED.value, {
                        'cancelled_reason': f"Not found on exchange: {reason}",
                        'cancelled_at': datetime.now(timezone.utc)
                    })
                    return True
                else:
                    raise
            
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False
    
    async def update_stop_loss(self, trade_id: uuid.UUID, new_stop_price: Decimal) -> bool:
        """
        Update stop loss price for a trade.
        
        Args:
            trade_id: Trade ID
            new_stop_price: New stop loss price
            
        Returns:
            True if updated successfully, False otherwise
        """
        try:
            # Find active stop loss order for this trade
            stop_loss_order = None
            for order_data in self._active_orders.values():
                if (order_data['trade_id'] == str(trade_id) and 
                    order_data['type'] == OrderType.STOP_LOSS.value and
                    order_data['status'] in [OrderStatus.SUBMITTED.value, OrderStatus.PARTIALLY_FILLED.value]):
                    stop_loss_order = order_data
                    break
            
            if not stop_loss_order:
                logger.warning(f"No active stop loss order found for trade {trade_id}")
                return False
            
            # Cancel existing stop loss
            if not await self.cancel_order(stop_loss_order['id'], "Updating stop loss"):
                return False
            
            # Create new stop loss order
            trade = await self.trade_repo.get_by_id(trade_id)
            if not trade:
                logger.error(f"Trade {trade_id} not found")
                return False
            
            # Determine side (opposite of trade side)
            stop_side = 'sell' if trade.side == 'BUY' else 'buy'
            
            result = await self.create_stop_loss_order(
                trade_id=trade_id,
                symbol=trade.asset.symbol,
                side=stop_side,
                quantity=trade.quantity,
                stop_price=new_stop_price
            )
            
            if result:
                # Update trade record
                await self.trade_repo.update_trade(trade_id, {
                    'stop_loss': new_stop_price
                })
                
                logger.info(f"✅ Stop loss updated for trade {trade_id}: {new_stop_price}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error updating stop loss for trade {trade_id}: {e}")
            return False
    
    async def _submit_market_order(self, order_id: str, symbol: str, side: str, quantity: Decimal) -> Optional[Dict[str, Any]]:
        """Submit market order to exchange with retry logic."""
        order_data = self._active_orders.get(order_id)
        if not order_data:
            return None
        
        for attempt in range(self._retry_attempts):
            try:
                order_data['attempts'] = attempt + 1
                
                # Update status to submitted
                await self._update_order_status(order_id, OrderStatus.SUBMITTED.value)
                
                # Submit to exchange
                result = await self.client.create_market_order(
                    symbol=symbol,
                    side=side,
                    amount=float(quantity)
                )
                
                if result:
                    # Update with exchange order ID and execution details
                    exchange_order_id = result.get('id')
                    filled_price = Decimal(str(result.get('average', 0)))
                    filled_quantity = Decimal(str(result.get('amount', 0)))
                    
                    order_data['exchange_order_id'] = exchange_order_id
                    order_data['filled_price'] = filled_price
                    order_data['filled_quantity'] = filled_quantity
                    
                    await self._update_order_status(order_id, OrderStatus.FILLED.value, {
                        'exchange_order_id': exchange_order_id,
                        'average_price': filled_price,
                        'filled_quantity': filled_quantity,
                        'fees': Decimal(str(result.get('fee', {}).get('cost', 0)))
                    })
                    
                    return {
                        'order_id': order_id,
                        'exchange_order_id': exchange_order_id,
                        'symbol': symbol,
                        'side': side,
                        'price': filled_price,
                        'quantity': filled_quantity,
                        'status': OrderStatus.FILLED.value,
                        'timestamp': datetime.now(timezone.utc)
                    }
                
            except TradingAPIError as e:
                logger.warning(f"Market order attempt {attempt + 1} failed: {e}")
                
                if attempt == self._retry_attempts - 1:
                    # Final attempt failed
                    await self._update_order_status(order_id, OrderStatus.REJECTED.value, {
                        'reject_reason': str(e)
                    })
                    return None
                
                # Wait before retry
                await asyncio.sleep(self._retry_delay * (2 ** attempt))
            
            except Exception as e:
                logger.error(f"Unexpected error in market order submission: {e}")
                await self._update_order_status(order_id, OrderStatus.REJECTED.value, {
                    'reject_reason': f"Unexpected error: {str(e)}"
                })
                return None
        
        return None
    
    async def _submit_stop_loss_order(self, order_id: str, symbol: str, side: str, quantity: Decimal, stop_price: Decimal) -> Optional[Dict[str, Any]]:
        """Submit stop loss order to exchange."""
        try:
            # Update status to submitted
            await self._update_order_status(order_id, OrderStatus.SUBMITTED.value)
            
            # Submit to exchange
            result = await self.client.create_stop_loss_order(
                symbol=symbol,
                side=side,
                amount=float(quantity),
                stop_price=float(stop_price)
            )
            
            if result:
                exchange_order_id = result.get('id')
                
                # Update order data
                order_data = self._active_orders[order_id]
                order_data['exchange_order_id'] = exchange_order_id
                
                await self._update_order_status(order_id, OrderStatus.SUBMITTED.value, {
                    'exchange_order_id': exchange_order_id
                })
                
                return {
                    'order_id': order_id,
                    'exchange_order_id': exchange_order_id,
                    'symbol': symbol,
                    'side': side,
                    'stop_price': stop_price,
                    'quantity': quantity,
                    'status': OrderStatus.SUBMITTED.value,
                    'timestamp': datetime.now(timezone.utc)
                }
            
        except Exception as e:
            logger.error(f"Error submitting stop loss order: {e}")
            await self._update_order_status(order_id, OrderStatus.REJECTED.value, {
                'reject_reason': str(e)
            })
        
        return None
    
    async def _submit_limit_order(self, order_id: str, symbol: str, side: str, quantity: Decimal, price: Decimal) -> Optional[Dict[str, Any]]:
        """Submit limit order to exchange."""
        try:
            # Update status to submitted
            await self._update_order_status(order_id, OrderStatus.SUBMITTED.value)
            
            # Submit to exchange
            result = await self.client.create_limit_order(
                symbol=symbol,
                side=side,
                amount=float(quantity),
                price=float(price)
            )
            
            if result:
                exchange_order_id = result.get('id')
                
                # Update order data
                order_data = self._active_orders[order_id]
                order_data['exchange_order_id'] = exchange_order_id
                
                await self._update_order_status(order_id, OrderStatus.SUBMITTED.value, {
                    'exchange_order_id': exchange_order_id
                })
                
                return {
                    'order_id': order_id,
                    'exchange_order_id': exchange_order_id,
                    'symbol': symbol,
                    'side': side,
                    'price': price,
                    'quantity': quantity,
                    'status': OrderStatus.SUBMITTED.value,
                    'timestamp': datetime.now(timezone.utc)
                }
            
        except Exception as e:
            logger.error(f"Error submitting limit order: {e}")
            await self._update_order_status(order_id, OrderStatus.REJECTED.value, {
                'reject_reason': str(e)
            })
        
        return None
    
    async def _monitor_orders(self):
        """Monitor active orders for status updates."""
        logger.info("Starting order monitoring")
        
        while self._is_running:
            try:
                # Check active orders
                orders_to_check = list(self._active_orders.keys())
                
                for order_id in orders_to_check:
                    if order_id not in self._active_orders:
                        continue
                    
                    await self._check_order_status(order_id)
                
                # Check for expired orders
                await self._check_expired_orders()
                
                # Wait before next check
                await asyncio.sleep(5)  # Check every 5 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in order monitoring: {e}")
                await asyncio.sleep(5)
        
        logger.info("Order monitoring stopped")
    
    async def _check_order_status(self, order_id: str):
        """Check status of a specific order."""
        try:
            order_data = self._active_orders.get(order_id)
            if not order_data:
                return
            
            exchange_order_id = order_data.get('exchange_order_id')
            if not exchange_order_id:
                return
            
            # Skip checking filled or cancelled orders
            if order_data['status'] in [OrderStatus.FILLED.value, OrderStatus.CANCELLED.value, OrderStatus.REJECTED.value]:
                return
            
            # Fetch order status from exchange
            try:
                order_status = await self.client.fetch_order(exchange_order_id, order_data['symbol'])
                
                if order_status:
                    await self._process_order_update(order_id, order_status)
                
            except TradingAPIError as e:
                if "Order not found" in str(e):
                    logger.warning(f"Order {order_id} not found on exchange, marking as cancelled")
                    await self._update_order_status(order_id, OrderStatus.CANCELLED.value, {
                        'cancelled_reason': "Not found on exchange"
                    })
                else:
                    logger.error(f"Error checking order status for {order_id}: {e}")
            
        except Exception as e:
            logger.error(f"Error checking order status for {order_id}: {e}")
    
    async def _process_order_update(self, order_id: str, exchange_order: Dict[str, Any]):
        """Process order status update from exchange."""
        try:
            order_data = self._active_orders.get(order_id)
            if not order_data:
                return
            
            exchange_status = exchange_order.get('status', '').upper()
            filled = Decimal(str(exchange_order.get('filled', 0)))
            remaining = Decimal(str(exchange_order.get('remaining', 0)))
            average_price = Decimal(str(exchange_order.get('average', 0)))
            
            # Map exchange status to our status
            if exchange_status == 'CLOSED' or filled >= order_data['quantity']:
                new_status = OrderStatus.FILLED.value
            elif filled > 0:
                new_status = OrderStatus.PARTIALLY_FILLED.value
            elif exchange_status == 'CANCELED':
                new_status = OrderStatus.CANCELLED.value
            else:
                new_status = OrderStatus.SUBMITTED.value
            
            # Update if status changed
            if new_status != order_data['status']:
                update_data = {
                    'filled_quantity': filled,
                    'average_price': average_price if average_price > 0 else None
                }
                
                await self._update_order_status(order_id, new_status, update_data)
                
                # Call callbacks
                await self._call_order_callbacks(order_id, new_status, exchange_order)
            
        except Exception as e:
            logger.error(f"Error processing order update for {order_id}: {e}")
    
    async def _check_expired_orders(self):
        """Check for orders that have exceeded timeout."""
        try:
            current_time = datetime.now(timezone.utc)
            timeout_threshold = timedelta(seconds=self._order_timeout)
            
            expired_orders = []
            for order_id, order_data in self._active_orders.items():
                if order_data['status'] in [OrderStatus.PENDING.value, OrderStatus.SUBMITTED.value]:
                    if current_time - order_data['created_at'] > timeout_threshold:
                        expired_orders.append(order_id)
            
            for order_id in expired_orders:
                logger.warning(f"Order {order_id} expired, attempting to cancel")
                await self.cancel_order(order_id, "Order timeout")
            
        except Exception as e:
            logger.error(f"Error checking expired orders: {e}")
    
    async def _update_order_status(self, order_id: str, status: str, additional_data: Optional[Dict] = None):
        """Update order status in database and memory."""
        try:
            # Update in memory
            if order_id in self._active_orders:
                self._active_orders[order_id]['status'] = status
                
                if additional_data:
                    self._active_orders[order_id].update(additional_data)
            
            # Update in database
            update_data = {'status': status}
            if additional_data:
                update_data.update(additional_data)
            
            await self.order_repo.update_order(uuid.UUID(order_id), update_data)
            
            # Remove from active orders if final status
            if status in [OrderStatus.FILLED.value, OrderStatus.CANCELLED.value, OrderStatus.REJECTED.value, OrderStatus.EXPIRED.value]:
                if order_id in self._active_orders:
                    del self._active_orders[order_id]
                
                if order_id in self._order_callbacks:
                    del self._order_callbacks[order_id]
            
        except Exception as e:
            logger.error(f"Error updating order status for {order_id}: {e}")
    
    async def _call_order_callbacks(self, order_id: str, status: str, exchange_order: Dict[str, Any]):
        """Call registered callbacks for order status changes."""
        try:
            callbacks = self._order_callbacks.get(order_id, [])
            for callback in callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(order_id, status, exchange_order)
                    else:
                        callback(order_id, status, exchange_order)
                except Exception as e:
                    logger.error(f"Error calling order callback: {e}")
        
        except Exception as e:
            logger.error(f"Error calling order callbacks for {order_id}: {e}")
    
    async def _load_active_orders(self):
        """Load active orders from database."""
        try:
            # Get pending and submitted orders
            from database.connection import get_session
            with get_session() as session:
                active_orders = self.order_repo.get_active_orders(session)
            
            for order in active_orders:
                self._active_orders[str(order.id)] = {
                    'id': str(order.id),
                    'trade_id': str(order.trade_id),
                    'symbol': order.trade.asset.symbol,
                    'type': order.type,
                    'side': order.side,
                    'quantity': order.quantity,
                    'price': order.price,
                    'status': order.status,
                    'exchange_order_id': order.exchange_order_id,
                    'created_at': order.timestamp,
                    'attempts': 0
                }
            
            logger.info(f"Loaded {len(self._active_orders)} active orders from database")
            
        except Exception as e:
            logger.error(f"Error loading active orders: {e}")
    
    async def get_active_orders(self) -> List[Dict[str, Any]]:
        """Get list of active orders."""
        return list(self._active_orders.values())
    
    async def get_orders_for_trade(self, trade_id: uuid.UUID) -> List[Dict[str, Any]]:
        """Get all orders for a specific trade."""
        return [
            order_data for order_data in self._active_orders.values()
            if order_data['trade_id'] == str(trade_id)
        ]
    
    async def get_order_stats(self) -> Dict[str, Any]:
        """Get order manager statistics."""
        try:
            total_orders = await self.order_repo.get_order_count()
            active_orders = len(self._active_orders)
            
            # Count by status
            status_counts = {}
            for order_data in self._active_orders.values():
                status = order_data['status']
                status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                'is_running': self._is_running,
                'active_orders': active_orders,
                'total_orders': total_orders,
                'status_counts': status_counts,
                'order_timeout': self._order_timeout,
                'retry_attempts': self._retry_attempts
            }
            
        except Exception as e:
            logger.error(f"Error getting order stats: {e}")
            return {}