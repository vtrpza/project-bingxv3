# database/repository.py
"""Repository pattern implementation for database operations."""

import logging
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, or_, func, String
from sqlalchemy.exc import SQLAlchemyError

from .models import Asset, MarketData, Indicator, Trade, Order, Signal, SystemConfig
from .connection import get_session

logger = logging.getLogger(__name__)


class BaseRepository:
    """Base repository with common CRUD operations."""
    
    def __init__(self, model_class):
        self.model_class = model_class
    
    def get_by_id(self, session: Session, id: str) -> Optional[Any]:
        """Get record by ID."""
        try:
            return session.query(self.model_class).filter(self.model_class.id == id).first()
        except SQLAlchemyError as e:
            logger.error(f"Error getting {self.model_class.__name__} by ID {id}: {e}")
            return None
    
    def get_all(self, session: Session, limit: Optional[int] = None) -> List[Any]:
        """Get all records with optional limit."""
        try:
            query = session.query(self.model_class)
            if limit is not None:
                query = query.limit(limit)
            return query.all()
        except SQLAlchemyError as e:
            logger.error(f"Error getting all {self.model_class.__name__}: {e}")
            return []
    
    def get_count(self, session: Session) -> int:
        """Get total count of records."""
        try:
            return session.query(self.model_class).count()
        except SQLAlchemyError as e:
            logger.error(f"Error counting {self.model_class.__name__}: {e}")
            return 0
    
    def get_paginated(self, session: Session, limit: int = 50, offset: int = 0) -> List[Any]:
        """Get paginated records."""
        try:
            return (session.query(self.model_class)
                   .offset(offset)
                   .limit(limit)
                   .all())
        except SQLAlchemyError as e:
            logger.error(f"Error getting paginated {self.model_class.__name__}: {e}")
            return []
    
    def create(self, session: Session, **kwargs) -> Optional[Any]:
        """Create new record."""
        try:
            instance = self.model_class(**kwargs)
            session.add(instance)
            session.flush()  # Get ID without committing
            return instance
        except SQLAlchemyError as e:
            logger.error(f"Error creating {self.model_class.__name__}: {e}")
            return None
    
    def update(self, session: Session, id: str, **kwargs) -> Optional[Any]:
        """Update record by ID."""
        try:
            instance = self.get_by_id(session, id)
            if instance:
                for key, value in kwargs.items():
                    setattr(instance, key, value)
                session.flush()
            return instance
        except SQLAlchemyError as e:
            logger.error(f"Error updating {self.model_class.__name__} {id}: {e}")
            return None
    
    def delete(self, session: Session, id: str) -> bool:
        """Delete record by ID."""
        try:
            instance = self.get_by_id(session, id)
            if instance:
                session.delete(instance)
                session.flush()
                return True
            return False
        except SQLAlchemyError as e:
            logger.error(f"Error deleting {self.model_class.__name__} {id}: {e}")
            return False


class AssetRepository(BaseRepository):
    """Repository for Asset operations."""
    
    def __init__(self):
        super().__init__(Asset)
    
    def get_by_symbol(self, session: Session, symbol: str) -> Optional[Asset]:
        """Get asset by symbol."""
        try:
            return session.query(Asset).filter(Asset.symbol == symbol.upper()).first()
        except SQLAlchemyError as e:
            logger.error(f"Error getting asset by symbol {symbol}: {e}")
            return None
    
    def get_valid_assets(self, session: Session, limit: int = None) -> List[Asset]:
        """Get all valid assets."""
        try:
            query = session.query(Asset).filter(Asset.is_valid == True)
            if limit is not None:
                query = query.limit(limit)
            return query.all()
        except SQLAlchemyError as e:
            logger.error(f"Error getting valid assets: {e}")
            return []

    def get_valid_assets_count(self, session: Session) -> int:
        """Get count of all valid assets."""
        try:
            return session.query(Asset).filter(Asset.is_valid == True).count()
        except SQLAlchemyError as e:
            logger.error(f"Error getting valid assets count: {e}")
            return 0
    
    def update_validation_status(self, session: Session, symbol: str, is_valid: bool, validation_data: Dict = None) -> Optional[Asset]:
        """Update asset validation status."""
        try:
            asset = self.get_by_symbol(session, symbol)
            if not asset:
                # Create new asset if it doesn't exist
                base, quote = symbol.split('/')
                asset = self.create(
                    session,
                    symbol=symbol,
                    base_currency=base,
                    quote_currency=quote,
                    is_valid=is_valid,
                    validation_data=validation_data,
                    last_validation=datetime.utcnow()
                )
            else:
                # Update existing asset
                asset.is_valid = is_valid
                asset.validation_data = validation_data
                asset.last_validation = datetime.utcnow()
                session.flush()
            
            return asset
        except SQLAlchemyError as e:
            logger.error(f"Error updating validation for asset {symbol}: {e}")
            return None
    
    def get_assets_with_sorting(self, session: Session, 
                               sort_by: str = "symbol", 
                               sort_direction: str = "asc",
                               filter_valid_only: bool = False,
                               search: Optional[str] = None,
                               limit: Optional[int] = None,
                               offset: int = 0,
                               risk_level_filter: Optional[str] = None,
                               priority_only: bool = False,
                               trading_enabled_only: bool = False) -> List[Asset]:
        """Get assets with sorting, filtering and search options."""
        try:
            query = session.query(Asset)
            
            # Apply search filter
            if search and search.strip():
                search_term = f"%{search.strip().upper()}%"
                query = query.filter(
                    or_(
                        Asset.symbol.ilike(search_term),
                        Asset.base_currency.ilike(search_term),
                        Asset.quote_currency.ilike(search_term)
                    )
                )
            
            # Apply validity filter
            if filter_valid_only:
                query = query.filter(Asset.is_valid == True)
            
            # Apply risk level filter
            if risk_level_filter and risk_level_filter.upper() != "ALL":
                risk_filter = f"%\"risk_level\":\"{risk_level_filter.upper()}\"%"
                query = query.filter(Asset.validation_data.cast(String).ilike(risk_filter))
            
            # Apply priority filter
            if priority_only:
                priority_filter = "%\"priority_asset\":true%"
                query = query.filter(Asset.validation_data.cast(String).ilike(priority_filter))
            
            # Apply trading enabled filter
            if trading_enabled_only:
                # Filter for assets with volume > 10000 and is_valid
                query = query.filter(
                    and_(
                        Asset.is_valid == True,
                        Asset.validation_data.cast(String).ilike('%"volume_24h_quote":%')
                    )
                )
            
            # Apply sorting with proper column mapping
            sort_mapping = {
                "symbol": Asset.symbol,
                "base_currency": Asset.base_currency, 
                "quote_currency": Asset.quote_currency,
                "is_valid": Asset.is_valid,
                "last_validation": Asset.last_validation,
                "created_at": Asset.created_at,
                "updated_at": Asset.updated_at
            }
            
            sort_column = sort_mapping.get(sort_by, Asset.symbol)
            
            if sort_direction.lower() == "desc":
                query = query.order_by(desc(sort_column))
            else:
                query = query.order_by(sort_column)
            
            # Apply pagination
            if offset > 0:
                query = query.offset(offset)
            if limit is not None:
                query = query.limit(limit)
                
            return query.all()
        except SQLAlchemyError as e:
            logger.error(f"Error getting sorted assets: {e}")
            return []
    
    def get_filtered_count(self, session: Session, filter_valid_only: bool = False, search: Optional[str] = None,
                          risk_level_filter: Optional[str] = None, priority_only: bool = False, 
                          trading_enabled_only: bool = False) -> int:
        """Get count of assets with filters applied."""
        try:
            query = session.query(Asset)
            
            # Apply search filter
            if search and search.strip():
                search_term = f"%{search.strip().upper()}%"
                query = query.filter(
                    or_(
                        Asset.symbol.ilike(search_term),
                        Asset.base_currency.ilike(search_term),
                        Asset.quote_currency.ilike(search_term)
                    )
                )
            
            # Apply validity filter
            if filter_valid_only:
                query = query.filter(Asset.is_valid == True)
            
            # Apply risk level filter
            if risk_level_filter and risk_level_filter.upper() != "ALL":
                risk_filter = f"%\"risk_level\":\"{risk_level_filter.upper()}\"%"
                query = query.filter(Asset.validation_data.cast(String).ilike(risk_filter))
            
            # Apply priority filter
            if priority_only:
                priority_filter = "%\"priority_asset\":true%"
                query = query.filter(Asset.validation_data.cast(String).ilike(priority_filter))
            
            # Apply trading enabled filter
            if trading_enabled_only:
                # Filter for assets with volume > 10000 and is_valid
                query = query.filter(
                    and_(
                        Asset.is_valid == True,
                        Asset.validation_data.cast(String).ilike('%"volume_24h_quote":%')
                    )
                )
                
            return query.count()
        except SQLAlchemyError as e:
            logger.error(f"Error counting filtered assets: {e}")
            return 0


class MarketDataRepository(BaseRepository):
    """Repository for MarketData operations."""
    
    def __init__(self):
        super().__init__(MarketData)
    
    def get_latest_data(self, session: Session, asset_id: str, timeframe: str, limit: int = 100) -> List[MarketData]:
        """Get latest market data for asset and timeframe with optimized query."""
        try:
            # Use index hint for PostgreSQL and optimized filtering
            query = (session.query(MarketData)
                   .filter(MarketData.asset_id == asset_id)
                   .filter(MarketData.timeframe == timeframe))
            
            # Add execution options for better performance
            query = query.execution_options(compiled_cache={})
            
            return (query.order_by(desc(MarketData.timestamp))
                   .limit(limit)
                   .all())
        except SQLAlchemyError as e:
            logger.error(f"Error getting latest market data: {e}")
            return []
    
    def get_data_range(self, session: Session, asset_id: str, timeframe: str, 
                      start_time: datetime, end_time: datetime) -> List[MarketData]:
        """Get market data within time range."""
        try:
            return (session.query(MarketData)
                   .filter(and_(
                       MarketData.asset_id == asset_id,
                       MarketData.timeframe == timeframe,
                       MarketData.timestamp >= start_time,
                       MarketData.timestamp <= end_time
                   ))
                   .order_by(MarketData.timestamp)
                   .all())
        except SQLAlchemyError as e:
            logger.error(f"Error getting market data range: {e}")
            return []
    
    def upsert_candle(self, session: Session, asset_id: str, timeframe: str, timestamp: datetime,
                     open_price: Decimal, high: Decimal, low: Decimal, close: Decimal, volume: Decimal) -> Optional[MarketData]:
        """Insert or update market data candle."""
        try:
            # Try to find existing candle
            existing = (session.query(MarketData)
                       .filter(and_(
                           MarketData.asset_id == asset_id,
                           MarketData.timeframe == timeframe,
                           MarketData.timestamp == timestamp
                       ))
                       .first())
            
            if existing:
                # Update existing
                existing.open = open_price
                existing.high = high
                existing.low = low
                existing.close = close
                existing.volume = volume
                session.flush()
                return existing
            else:
                # Create new
                return self.create(
                    session,
                    asset_id=asset_id,
                    timeframe=timeframe,
                    timestamp=timestamp,
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume
                )
        except SQLAlchemyError as e:
            logger.error(f"Error upserting market data: {e}")
            return None


class IndicatorRepository(BaseRepository):
    """Repository for Indicator operations."""
    
    def __init__(self):
        super().__init__(Indicator)
    
    def get_latest_indicators(self, session: Session, asset_id: str = None) -> List[Indicator]:
        """Get latest indicators for all assets or specific asset."""
        try:
            query = session.query(Indicator)
            
            if asset_id:
                query = query.filter(Indicator.asset_id == asset_id)
            
            # Get latest indicator for each asset/timeframe combination
            subquery = (session.query(
                           Indicator.asset_id,
                           Indicator.timeframe,
                           func.max(Indicator.timestamp).label('max_timestamp')
                       )
                       .group_by(Indicator.asset_id, Indicator.timeframe)
                       .subquery())
            
            return (query.join(subquery, and_(
                       Indicator.asset_id == subquery.c.asset_id,
                       Indicator.timeframe == subquery.c.timeframe,
                       Indicator.timestamp == subquery.c.max_timestamp
                   ))
                   .all())
        except SQLAlchemyError as e:
            logger.error(f"Error getting latest indicators: {e}")
            return []

    def get_latest_indicators_by_timeframe(self, session: Session, asset_id: str, timeframe: str) -> Optional[Indicator]:
        """Get latest indicator for specific asset and timeframe."""
        try:
            return (session.query(Indicator)
                   .filter(and_(
                       Indicator.asset_id == asset_id,
                       Indicator.timeframe == timeframe
                   ))
                   .order_by(desc(Indicator.timestamp))
                   .first())
        except SQLAlchemyError as e:
            logger.error(f"Error getting latest indicators by timeframe: {e}")
            return None

    def get_latest_indicators_for_all_assets(self, session: Session, limit: int = 100) -> List[Indicator]:
        """Get the very latest indicator for each asset, across all timeframes."""
        try:
            # Subquery to find the maximum timestamp for each asset_id
            subquery = (
                session.query(
                    Indicator.asset_id,
                    func.max(Indicator.timestamp).label('max_timestamp')
                )
                .group_by(Indicator.asset_id)
                .subquery()
            )

            # Join with the main Indicator table to get the full indicator records
            # for the latest timestamp of each asset
            query = (
                session.query(Indicator)
                .join(
                    subquery,
                    and_(
                        Indicator.asset_id == subquery.c.asset_id,
                        Indicator.timestamp == subquery.c.max_timestamp
                    )
                )
                .order_by(desc(Indicator.timestamp))
            )
            
            if limit:
                query = query.limit(limit)
                
            return query.all()
        except SQLAlchemyError as e:
            logger.error(f"Error getting latest indicators for all assets: {e}")
            return []
    
    def upsert_indicators(self, session: Session, asset_id: str, timeframe: str, timestamp: datetime,
                         mm1: Decimal = None, center: Decimal = None, rsi: Decimal = None,
                         volume_sma: Decimal = None, additional_data: Dict = None) -> Optional[Indicator]:
        """Insert or update technical indicators."""
        try:
            # Validate numeric values to prevent overflow
            if volume_sma is not None and abs(volume_sma) >= Decimal('10') ** 22:
                # Volume SMA too large for Numeric(30, 8), truncate/cap it
                logger.warning(f"Volume SMA value {volume_sma} is too large, capping at 10^21")
                volume_sma = Decimal('10') ** 21 if volume_sma > 0 else -(Decimal('10') ** 21)
            
            # Try to find existing indicators
            existing = (session.query(Indicator)
                       .filter(and_(
                           Indicator.asset_id == asset_id,
                           Indicator.timeframe == timeframe,
                           Indicator.timestamp == timestamp
                       ))
                       .first())
            
            if existing:
                # Update existing
                if mm1 is not None:
                    existing.mm1 = mm1
                if center is not None:
                    existing.center = center
                if rsi is not None:
                    existing.rsi = rsi
                if volume_sma is not None:
                    existing.volume_sma = volume_sma
                if additional_data is not None:
                    existing.additional_data = additional_data
                session.flush()
                return existing
            else:
                # Create new
                return self.create(
                    session,
                    asset_id=asset_id,
                    timeframe=timeframe,
                    timestamp=timestamp,
                    mm1=mm1,
                    center=center,
                    rsi=rsi,
                    volume_sma=volume_sma,
                    additional_data=additional_data
                )
        except SQLAlchemyError as e:
            logger.error(f"Error upserting indicators: {e}")
            # Rollback the session to prevent "transaction rolled back" error
            session.rollback()
            return None


class TradeRepository(BaseRepository):
    """Repository for Trade operations."""
    
    def __init__(self):
        super().__init__(Trade)
    
    def get_open_positions(self, session: Session, asset_id: str = None) -> List[Trade]:
        """Get all open positions (trades)."""
        try:
            query = session.query(Trade).filter(Trade.status == 'OPEN')
            if asset_id:
                query = query.filter(Trade.asset_id == asset_id)
            return query.order_by(desc(Trade.entry_time)).all()
        except SQLAlchemyError as e:
            logger.error(f"Error getting open positions: {e}")
            return []
    
    def get_recent_trades(self, session: Session, days: int = 30, asset_id: str = None) -> List[Trade]:
        """Get recent trades within specified days."""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            query = session.query(Trade).filter(Trade.entry_time >= cutoff_date)
            if asset_id:
                query = query.filter(Trade.asset_id == asset_id)
            return query.order_by(desc(Trade.entry_time)).all()
        except SQLAlchemyError as e:
            logger.error(f"Error getting recent trades: {e}")
            return []
    
    def create_trade(self, session: Session, asset_id: str, side: str, entry_price: Decimal,
                    quantity: Decimal, stop_loss: Decimal = None, take_profit: Decimal = None,
                    entry_reason: str = None) -> Optional[Trade]:
        """Create new trade."""
        try:
            return self.create(
                session,
                asset_id=asset_id,
                side=side,
                entry_price=entry_price,
                quantity=quantity,
                stop_loss=stop_loss,
                take_profit=take_profit,
                entry_reason=entry_reason
            )
        except SQLAlchemyError as e:
            logger.error(f"Error creating trade: {e}")
            return None
    
    def close_trade(self, session: Session, trade_id: str, exit_price: Decimal,
                   exit_reason: str = None, fees: Decimal = None) -> Optional[Trade]:
        """Close a trade with exit data."""
        try:
            trade = self.get_by_id(session, trade_id)
            if trade and trade.status == 'OPEN':
                trade.status = 'CLOSED'
                trade.exit_time = datetime.utcnow()
                trade.exit_price = exit_price
                trade.exit_reason = exit_reason
                trade.fees = fees or Decimal('0')
                
                # Calculate P&L
                trade.pnl = trade.calculate_pnl(exit_price) - trade.fees
                if trade.entry_price > 0:
                    trade.pnl_percentage = (trade.pnl / (trade.entry_price * trade.quantity)) * 100
                
                session.flush()
                return trade
            return None
        except SQLAlchemyError as e:
            logger.error(f"Error closing trade {trade_id}: {e}")
            return None
    
    def get_trade_count(self, session: Session, asset_id: str = None) -> int:
        """Get total trade count."""
        try:
            query = session.query(Trade)
            if asset_id:
                query = query.filter(Trade.asset_id == asset_id)
            return query.count()
        except SQLAlchemyError as e:
            logger.error(f"Error getting trade count: {e}")
            return 0
    
    def get_performance_stats(self, session: Session, asset_id: str = None, days: int = 30) -> Dict[str, Any]:
        """Get trading performance statistics."""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            query = session.query(Trade).filter(
                and_(Trade.status == 'CLOSED', Trade.entry_time >= cutoff_date)
            )
            if asset_id:
                query = query.filter(Trade.asset_id == asset_id)
            
            trades = query.all()
            
            if not trades:
                return {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'win_rate': 0,
                    'total_pnl': 0,
                    'avg_pnl': 0,
                    'max_win': 0,
                    'max_loss': 0
                }
            
            winning_trades = [t for t in trades if t.pnl and t.pnl > 0]
            losing_trades = [t for t in trades if t.pnl and t.pnl < 0]
            
            total_pnl = sum(t.pnl for t in trades if t.pnl)
            
            return {
                'total_trades': len(trades),
                'winning_trades': len(winning_trades),
                'losing_trades': len(losing_trades),
                'win_rate': len(winning_trades) / len(trades) * 100 if trades else 0,
                'total_pnl': float(total_pnl),
                'avg_pnl': float(total_pnl / len(trades)) if trades else 0,
                'max_win': float(max(t.pnl for t in winning_trades)) if winning_trades else 0,
                'max_loss': float(min(t.pnl for t in losing_trades)) if losing_trades else 0
            }
        except SQLAlchemyError as e:
            logger.error(f"Error getting performance stats: {e}")
            return {}
    
    def update_trade(self, session: Session, trade_id: str, update_data: Dict[str, Any]) -> Optional[Trade]:
        """Update trade with new data."""
        try:
            return self.update(session, trade_id, **update_data)
        except SQLAlchemyError as e:
            logger.error(f"Error updating trade {trade_id}: {e}")
            return None
    
    def get_closed_trades(self, session: Session, limit: int = 100, asset_id: str = None) -> List[Trade]:
        """Get closed trades with optional limit."""
        try:
            query = session.query(Trade).filter(Trade.status == 'CLOSED')
            if asset_id:
                query = query.filter(Trade.asset_id == asset_id)
            return query.order_by(desc(Trade.exit_time)).limit(limit).all()
        except SQLAlchemyError as e:
            logger.error(f"Error getting closed trades: {e}")
            return []
    
    def get_trades_by_date(self, session: Session, target_date, asset_id: str = None) -> List[Trade]:
        """Get trades for a specific date."""
        try:
            from datetime import datetime as dt, date, timezone
            
            # Convert date to datetime if needed
            if isinstance(target_date, dt):
                # It's already a datetime
                start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
                end_of_day = target_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            elif isinstance(target_date, date):
                # It's a date, convert to datetime with timezone
                start_of_day = dt.combine(target_date, dt.min.time()).replace(tzinfo=timezone.utc)
                end_of_day = dt.combine(target_date, dt.max.time()).replace(tzinfo=timezone.utc)
            else:
                raise ValueError(f"Unsupported date type: {type(target_date)}")
            
            query = session.query(Trade).filter(
                and_(
                    Trade.entry_time >= start_of_day,
                    Trade.entry_time <= end_of_day
                )
            )
            if asset_id:
                query = query.filter(Trade.asset_id == asset_id)
            return query.order_by(desc(Trade.entry_time)).all()
        except SQLAlchemyError as e:
            logger.error(f"Error getting trades by date {target_date}: {e}")
            return []

    def get_trades_since(self, session: Session, start_time: datetime, asset_id: str = None) -> List[Trade]:
        """Get trades that occurred since a specific timestamp."""
        try:
            query = session.query(Trade).filter(Trade.entry_time >= start_time)
            if asset_id:
                query = query.filter(Trade.asset_id == asset_id)
            return query.order_by(desc(Trade.entry_time)).all()
        except SQLAlchemyError as e:
            logger.error(f"Error getting trades since {start_time}: {e}")
            return []
    
    def get_trades(self, session: Session, symbol: str = None, status: str = None, limit: int = 50) -> List[Trade]:
        """Get trades with optional filtering by symbol and status."""
        try:
            from sqlalchemy.orm import joinedload
            
            # Always join with Asset to load the asset relationship
            query = session.query(Trade).options(joinedload(Trade.asset))
            
            # Filter by symbol if provided (join with Asset table)
            if symbol:
                query = query.join(Asset).filter(Asset.symbol == symbol.upper())
            
            # Filter by status if provided
            if status:
                query = query.filter(Trade.status == status.upper())
            
            # Order by entry time (most recent first) and apply limit
            query = query.order_by(desc(Trade.entry_time))
            if limit:
                query = query.limit(limit)
                
            return query.all()
        except SQLAlchemyError as e:
            logger.error(f"Error getting trades (symbol={symbol}, status={status}, limit={limit}): {e}")
            return []
    
    def get_open_trades(self, session: Session = None) -> List[Trade]:
        """Get all open trades - compatibility wrapper for get_open_positions.""" 
        try:
            if session is None:
                # If no session provided, create one (for backward compatibility)
                with get_session() as db:
                    return self.get_open_positions(db)
            else:
                return self.get_open_positions(session)
        except Exception as e:
            logger.error(f"Error getting open trades: {e}")
            return []
    
    def get_open_trades_by_asset(self, session: Session, asset_id: str) -> List[Trade]:
        """Get open trades for a specific asset."""
        try:
            return self.get_open_positions(session, asset_id=asset_id)
        except Exception as e:
            logger.error(f"Error getting open trades by asset {asset_id}: {e}")
            return []
    
    def get_trades_today(self, session: Session = None) -> List[Trade]:
        """Get trades from today."""
        try:
            from datetime import date
            if session is None:
                with get_session() as db:
                    return self.get_trades_by_date(db, date.today())
            else:
                return self.get_trades_by_date(session, date.today())
        except Exception as e:
            logger.error(f"Error getting today's trades: {e}")
            return []
    
    def update_trade_quantity(self, trade_id: str, new_quantity: float, realized_pnl: float = None):
        """Update trade quantity and add realized P&L (for partial closes)."""
        try:
            with get_session() as session:
                trade = self.get_by_id(session, trade_id)
                if trade:
                    trade.quantity = new_quantity
                    if realized_pnl:
                        # Add realized P&L to fees field as a running total
                        current_realized = trade.fees or Decimal('0')
                        trade.fees = current_realized + Decimal(str(realized_pnl))
                    session.commit()
                    return trade
            return None
        except Exception as e:
            logger.error(f"Error updating trade quantity {trade_id}: {e}")
            return None


class SignalRepository(BaseRepository):
    """Repository for Signal operations."""
    
    def __init__(self):
        super().__init__(Signal)

    def _convert_decimals_to_float(self, data: Any) -> Any:
        """Recursively converts Decimal objects in a dictionary or list to floats."""
        if isinstance(data, dict):
            return {k: self._convert_decimals_to_float(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._convert_decimals_to_float(elem) for elem in data]
        elif isinstance(data, Decimal):
            return float(data)
        return data
    
    def create_signal(self, session: Session, asset_id: str, signal_type: str, strength: Decimal,
                     rules_triggered: List[str], indicators_snapshot: Dict, trade_id: str = None) -> Optional[Signal]:
        """Create new trading signal."""
        try:
            return self.create(
                session,
                asset_id=asset_id,
                timestamp=datetime.utcnow(),
                signal_type=signal_type,
                strength=strength,
                rules_triggered=rules_triggered,
                indicators_snapshot=self._convert_decimals_to_float(indicators_snapshot),
                trade_id=trade_id
            )
        except SQLAlchemyError as e:
            logger.error(f"Error creating signal: {e}")
            return None
    
    def get_recent_signals(self, session: Session, hours: int = 24, asset_id: str = None, limit: int = None) -> List[Signal]:
        """Get recent signals within specified hours."""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            query = session.query(Signal).filter(Signal.timestamp >= cutoff_time)
            if asset_id:
                query = query.filter(Signal.asset_id == asset_id)
            query = query.order_by(desc(Signal.timestamp))
            if limit is not None:
                query = query.limit(limit)
            return query.all()
        except SQLAlchemyError as e:
            logger.error(f"Error getting recent signals: {e}")
            return []
    
    def get_pending_signals(self, session: Session, limit: int = 50) -> List[Signal]:
        """Get pending signals that haven't been processed."""
        try:
            # Since Signal model doesn't have a processed flag, return recent signals
            # This method exists for compatibility with signal processing code
            return (session.query(Signal)
                   .order_by(desc(Signal.timestamp))
                   .limit(limit)
                   .all())
        except SQLAlchemyError as e:
            logger.error(f"Error getting pending signals: {e}")
            return []

    def get_active_signals_count(self, session: Session) -> int:
        """Get count of unprocessed signals."""
        try:
            # Assuming 'is_processed' is a boolean field in the Signal model
            # If not, adjust the filter condition based on how unprocessed signals are identified
            return session.query(Signal).filter(Signal.is_processed == False).count()
        except SQLAlchemyError as e:
            logger.error(f"Error getting active signals count: {e}")
            return 0


class OrderRepository(BaseRepository):
    """Repository for Order operations."""
    
    def __init__(self):
        super().__init__(Order)
    
    def get_orders_by_trade(self, session: Session, trade_id: str) -> List[Order]:
        """Get all orders for a specific trade."""
        try:
            return session.query(Order).filter(Order.trade_id == trade_id).all()
        except SQLAlchemyError as e:
            logger.error(f"Error getting orders for trade {trade_id}: {e}")
            return []
    
    def get_pending_orders(self, session: Session) -> List[Order]:
        """Get all pending orders."""
        try:
            return session.query(Order).filter(Order.status.in_(['PENDING', 'OPEN', 'NEW'])).all()
        except SQLAlchemyError as e:
            logger.error(f"Error getting pending orders: {e}")
            return []
    
    def get_active_orders(self, session: Session) -> List[Order]:
        """Get all active orders (submitted, partially filled)."""
        try:
            return session.query(Order).filter(
                Order.status.in_(['SUBMITTED', 'PARTIALLY_FILLED', 'PENDING'])
            ).all()
        except SQLAlchemyError as e:
            logger.error(f"Error getting active orders: {e}")
            return []
    
    def create_order(self, session: Session, order_data: Dict[str, Any]) -> Optional[Order]:
        """Create new order."""
        try:
            return self.create(session, **order_data)
        except SQLAlchemyError as e:
            logger.error(f"Error creating order: {e}")
            return None
    
    def update_order(self, session: Session, order_id: str, update_data: Dict[str, Any]) -> Optional[Order]:
        """Update order with new data."""
        try:
            return self.update(session, order_id, **update_data)
        except SQLAlchemyError as e:
            logger.error(f"Error updating order {order_id}: {e}")
            return None
    
    def get_order_count(self, session: Session) -> int:
        """Get total order count."""
        try:
            return session.query(Order).count()
        except SQLAlchemyError as e:
            logger.error(f"Error getting order count: {e}")
            return 0
    
    def update_order_status(self, session: Session, order_id: str, status: str, 
                           filled_quantity: Decimal = None, average_price: Decimal = None,
                           fees: Decimal = None) -> Optional[Order]:
        """Update order status and execution details."""
        try:
            order = self.get_by_id(session, order_id)
            if order:
                order.status = status
                if filled_quantity is not None:
                    order.filled_quantity = filled_quantity
                if average_price is not None:
                    order.average_price = average_price
                if fees is not None:
                    order.fees = fees
                order.updated_at = datetime.utcnow()
                session.flush()
            return order
        except SQLAlchemyError as e:
            logger.error(f"Error updating order {order_id}: {e}")
            return None


class SystemConfigRepository(BaseRepository):
    """Repository for SystemConfig operations."""
    
    def __init__(self):
        super().__init__(SystemConfig)
    
    def get_config(self, session: Session, key: str, default_value: Any = None) -> Any:
        """Get configuration value by key."""
        try:
            config = session.query(SystemConfig).filter(SystemConfig.key == key.lower()).first()
            return config.value if config else default_value
        except SQLAlchemyError as e:
            logger.error(f"Error getting config {key}: {e}")
            return default_value
    
    def set_config(self, session: Session, key: str, value: Any, description: str = None) -> Optional[SystemConfig]:
        """Set configuration value."""
        try:
            config = session.query(SystemConfig).filter(SystemConfig.key == key.lower()).first()
            if config:
                # Update existing
                config.value = value
                config.description = description
                config.updated_at = datetime.utcnow()
                session.flush()
                return config
            else:
                # Create new
                return self.create(
                    session,
                    key=key.lower(),
                    value=value,
                    description=description
                )
        except SQLAlchemyError as e:
            logger.error(f"Error setting config {key}: {e}")
            return None


class BatchOperationMixin:
    """Mixin for optimized batch database operations."""
    
    def batch_insert(self, session: Session, items: List[Dict], batch_size: int = 100) -> int:
        """Perform optimized batch insert with chunking."""
        try:
            if not items:
                return 0
            
            total_inserted = 0
            # Process in chunks to avoid memory issues and improve performance
            for i in range(0, len(items), batch_size):
                chunk = items[i:i + batch_size]
                objects = [self.model_class(**item) for item in chunk]
                session.add_all(objects)
                session.flush()  # Flush each batch
                total_inserted += len(chunk)
                
                # Clear session cache periodically to prevent memory buildup
                if i > 0 and i % (batch_size * 10) == 0:
                    session.expunge_all()
            
            return total_inserted
        except SQLAlchemyError as e:
            logger.error(f"Error in batch insert: {e}")
            session.rollback()
            return 0
    
    def batch_update(self, session: Session, updates: List[Tuple[str, Dict]], batch_size: int = 50) -> int:
        """Perform optimized batch updates."""
        try:
            if not updates:
                return 0
            
            total_updated = 0
            # Process in chunks
            for i in range(0, len(updates), batch_size):
                chunk = updates[i:i + batch_size]
                
                for item_id, update_data in chunk:
                    session.query(self.model_class).filter(
                        self.model_class.id == item_id
                    ).update(update_data, synchronize_session=False)
                
                session.flush()
                total_updated += len(chunk)
            
            return total_updated
        except SQLAlchemyError as e:
            logger.error(f"Error in batch update: {e}")
            session.rollback()
            return 0
    
    def bulk_upsert(self, session: Session, items: List[Dict], conflict_columns: List[str], 
                   update_columns: List[str] = None, batch_size: int = 100) -> int:
        """PostgreSQL-specific bulk upsert operation using ON CONFLICT."""
        try:
            if not items or not hasattr(session.get_bind(), 'dialect') or 'postgresql' not in str(session.get_bind().dialect.name):
                # Fallback to regular batch operations for non-PostgreSQL
                return self.batch_insert(session, items, batch_size)
            
            from sqlalchemy.dialects.postgresql import insert
            
            total_upserted = 0
            for i in range(0, len(items), batch_size):
                chunk = items[i:i + batch_size]
                
                stmt = insert(self.model_class.__table__).values(chunk)
                
                # Create ON CONFLICT DO UPDATE clause
                if update_columns:
                    update_dict = {col: stmt.excluded[col] for col in update_columns}
                    stmt = stmt.on_conflict_do_update(
                        index_elements=conflict_columns,
                        set_=update_dict
                    )
                else:
                    stmt = stmt.on_conflict_do_nothing(index_elements=conflict_columns)
                
                result = session.execute(stmt)
                total_upserted += result.rowcount
                session.flush()
            
            return total_upserted
        except Exception as e:
            logger.error(f"Error in bulk upsert: {e}")
            session.rollback()
            return 0


# Enhanced repository classes with batch operations
class OptimizedAssetRepository(AssetRepository, BatchOperationMixin):
    """Asset repository with batch operation optimizations."""
    
    def bulk_update_validation_status(self, session: Session, 
                                     validations: List[Tuple[str, bool, Dict]], 
                                     batch_size: int = 50) -> int:
        """Bulk update validation status for multiple assets."""
        try:
            total_updated = 0
            for i in range(0, len(validations), batch_size):
                chunk = validations[i:i + batch_size]
                
                for symbol, is_valid, validation_data in chunk:
                    # Use merge for efficient upsert
                    asset = session.merge(Asset(
                        symbol=symbol.upper(),
                        is_valid=is_valid,
                        validation_data=validation_data,
                        last_validation=datetime.utcnow()
                    ))
                    session.add(asset)
                
                session.flush()
                total_updated += len(chunk)
            
            return total_updated
        except SQLAlchemyError as e:
            logger.error(f"Error in bulk validation update: {e}")
            session.rollback()
            return 0


class OptimizedMarketDataRepository(MarketDataRepository, BatchOperationMixin):
    """Market data repository with batch optimizations."""
    
    def bulk_insert_candles(self, session: Session, candles_data: List[Dict], 
                           batch_size: int = 200) -> int:
        """Efficiently insert multiple candles with conflict handling."""
        try:
            if not candles_data:
                return 0
            
            # Use PostgreSQL-specific upsert if available
            if hasattr(session.get_bind(), 'dialect') and 'postgresql' in str(session.get_bind().dialect.name):
                return self.bulk_upsert(
                    session, candles_data,
                    conflict_columns=['asset_id', 'timestamp', 'timeframe'],
                    update_columns=['open', 'high', 'low', 'close', 'volume'],
                    batch_size=batch_size
                )
            else:
                # Fallback for other databases
                return self.batch_insert(session, candles_data, batch_size)
                
        except Exception as e:
            logger.error(f"Error in bulk candle insert: {e}")
            session.rollback()
            return 0


class OptimizedIndicatorRepository(IndicatorRepository, BatchOperationMixin):
    """Indicator repository with batch optimizations."""
    
    def bulk_insert_indicators(self, session: Session, indicators_data: List[Dict], 
                              batch_size: int = 150) -> int:
        """Efficiently insert multiple indicators with conflict handling."""
        try:
            if not indicators_data:
                return 0
            
            # Validate and clean data before bulk insert
            cleaned_data = []
            for data in indicators_data:
                # Handle volume_sma overflow (from original code)
                if 'volume_sma' in data and data['volume_sma'] is not None:
                    if abs(data['volume_sma']) >= Decimal('10') ** 22:
                        data['volume_sma'] = Decimal('10') ** 21 if data['volume_sma'] > 0 else -(Decimal('10') ** 21)
                cleaned_data.append(data)
            
            # Use PostgreSQL-specific upsert if available
            if hasattr(session.get_bind(), 'dialect') and 'postgresql' in str(session.get_bind().dialect.name):
                return self.bulk_upsert(
                    session, cleaned_data,
                    conflict_columns=['asset_id', 'timestamp', 'timeframe'],
                    update_columns=['mm1', 'center', 'rsi', 'volume_sma', 'additional_data'],
                    batch_size=batch_size
                )
            else:
                return self.batch_insert(session, cleaned_data, batch_size)
                
        except Exception as e:
            logger.error(f"Error in bulk indicator insert: {e}")
            session.rollback()
            return 0