# database/models.py
"""SQLAlchemy models for BingX Trading Bot database schema."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    Column, String, Boolean, DateTime, JSON, Numeric, Integer,
    Text, ForeignKey, ARRAY, CheckConstraint, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func

Base = declarative_base()


class Asset(Base):
    """Model for trading assets (cryptocurrency pairs)."""
    
    __tablename__ = 'assets'
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Asset information
    symbol = Column(String(20), unique=True, nullable=False, index=True)
    base_currency = Column(String(10), nullable=False)
    quote_currency = Column(String(10), nullable=False)
    
    # Validation status
    is_valid = Column(Boolean, default=True, index=True)
    min_order_size = Column(Numeric(20, 8))
    last_validation = Column(DateTime(timezone=True))
    validation_data = Column(JSONB)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    # Relationships
    market_data = relationship("MarketData", back_populates="asset", cascade="all, delete-orphan")
    indicators = relationship("Indicator", back_populates="asset", cascade="all, delete-orphan")
    trades = relationship("Trade", back_populates="asset", cascade="all, delete-orphan")
    signals = relationship("Signal", back_populates="asset", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Asset(symbol='{self.symbol}', valid={self.is_valid})>"

    @validates('symbol')
    def validate_symbol(self, key, symbol):
        if not symbol or len(symbol) > 20:
            raise ValueError("Symbol must be non-empty and max 20 chars")
        return symbol.upper()


class MarketData(Base):
    """Model for OHLCV market data."""
    
    __tablename__ = 'market_data'
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign key
    asset_id = Column(UUID(as_uuid=True), ForeignKey('assets.id'), nullable=False)
    
    # Market data
    timestamp = Column(DateTime(timezone=True), nullable=False)
    timeframe = Column(String(10), nullable=False)  # '1h', '2h', '4h', etc.
    open = Column(Numeric(20, 8), nullable=False)
    high = Column(Numeric(20, 8), nullable=False)
    low = Column(Numeric(20, 8), nullable=False)
    close = Column(Numeric(20, 8), nullable=False)
    volume = Column(Numeric(20, 8), nullable=False)
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    
    # Relationships
    asset = relationship("Asset", back_populates="market_data")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('asset_id', 'timestamp', 'timeframe', name='uq_market_data_asset_time_tf'),
        Index('idx_market_data_asset_time', 'asset_id', 'timestamp'),
    )
    
    def __repr__(self):
        return f"<MarketData(asset={self.asset_id}, time={self.timestamp}, tf={self.timeframe})>"

    @validates('timeframe')
    def validate_timeframe(self, key, timeframe):
        valid_timeframes = ['spot', '1h', '2h', '4h', '1d']
        if timeframe not in valid_timeframes:
            raise ValueError(f"Timeframe must be one of: {valid_timeframes}")
        return timeframe


class Indicator(Base):
    """Model for technical indicators."""
    
    __tablename__ = 'indicators'
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign key
    asset_id = Column(UUID(as_uuid=True), ForeignKey('assets.id'), nullable=False)
    
    # Indicator data
    timestamp = Column(DateTime(timezone=True), nullable=False)
    timeframe = Column(String(10), nullable=False)
    mm1 = Column(Numeric(20, 8))  # Fast EMA (9 periods)
    center = Column(Numeric(20, 8))  # Slow EMA (21 periods)
    rsi = Column(Numeric(5, 2))  # RSI (14 periods)
    volume_sma = Column(Numeric(20, 8))  # Volume SMA
    additional_data = Column(JSONB)  # For extra indicators
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    
    # Relationships
    asset = relationship("Asset", back_populates="indicators")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('asset_id', 'timestamp', 'timeframe', name='uq_indicators_asset_time_tf'),
        Index('idx_indicators_asset_time', 'asset_id', 'timestamp'),
    )
    
    def __repr__(self):
        return f"<Indicator(asset={self.asset_id}, mm1={self.mm1}, center={self.center}, rsi={self.rsi})>"

    @validates('rsi')
    def validate_rsi(self, key, rsi):
        if rsi is not None and (rsi < 0 or rsi > 100):
            raise ValueError("RSI must be between 0 and 100")
        return rsi


class Trade(Base):
    """Model for trading operations."""
    
    __tablename__ = 'trades'
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign key
    asset_id = Column(UUID(as_uuid=True), ForeignKey('assets.id'), nullable=False)
    
    # Trade data
    side = Column(String(10), nullable=False)  # 'BUY' or 'SELL'
    entry_price = Column(Numeric(20, 8), nullable=False)
    quantity = Column(Numeric(20, 8), nullable=False)
    stop_loss = Column(Numeric(20, 8))
    take_profit = Column(Numeric(20, 8))
    status = Column(String(20), nullable=False, default='OPEN', index=True)
    entry_reason = Column(String(50))
    
    # Timing
    entry_time = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    exit_time = Column(DateTime(timezone=True))
    
    # Exit data
    exit_price = Column(Numeric(20, 8))
    exit_reason = Column(String(50))
    
    # P&L calculations
    pnl = Column(Numeric(20, 8))
    pnl_percentage = Column(Numeric(10, 4))
    fees = Column(Numeric(20, 8))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    # Relationships
    asset = relationship("Asset", back_populates="trades")
    orders = relationship("Order", back_populates="trade", cascade="all, delete-orphan")
    signal = relationship("Signal", back_populates="trade", uselist=False)
    
    # Constraints
    __table_args__ = (
        CheckConstraint("side IN ('BUY', 'SELL')", name='ck_trade_side'),
        CheckConstraint("status IN ('OPEN', 'CLOSED', 'CANCELLED')", name='ck_trade_status'),
        Index('idx_trades_asset', 'asset_id'),
        Index('idx_trades_entry_time', 'entry_time'),
    )
    
    def __repr__(self):
        return f"<Trade(asset={self.asset_id}, side={self.side}, status={self.status}, entry_price={self.entry_price})>"

    @validates('side')
    def validate_side(self, key, side):
        if side not in ['BUY', 'SELL']:
            raise ValueError("Side must be 'BUY' or 'SELL'")
        return side

    @validates('status')
    def validate_status(self, key, status):
        valid_statuses = ['OPEN', 'CLOSED', 'CANCELLED']
        if status not in valid_statuses:
            raise ValueError(f"Status must be one of: {valid_statuses}")
        return status

    def calculate_pnl(self, current_price: Optional[Decimal] = None) -> Decimal:
        """Calculate current P&L for the trade."""
        if self.status == 'CLOSED' and self.exit_price:
            price_diff = self.exit_price - self.entry_price
        elif current_price:
            price_diff = current_price - self.entry_price
        else:
            return Decimal('0')
        
        if self.side == 'SELL':
            price_diff = -price_diff
            
        return price_diff * self.quantity


class Order(Base):
    """Model for individual orders within trades."""
    
    __tablename__ = 'orders'
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign key
    trade_id = Column(UUID(as_uuid=True), ForeignKey('trades.id'), nullable=False)
    
    # Order data
    exchange_order_id = Column(String(100), unique=True)
    type = Column(String(20), nullable=False)  # 'MARKET', 'LIMIT', 'STOP_LOSS', etc.
    side = Column(String(10), nullable=False)  # 'BUY' or 'SELL'
    price = Column(Numeric(20, 8))
    quantity = Column(Numeric(20, 8), nullable=False)
    status = Column(String(20), nullable=False, index=True)
    
    # Execution data
    filled_quantity = Column(Numeric(20, 8))
    average_price = Column(Numeric(20, 8))
    fees = Column(Numeric(20, 8))
    
    # Timestamps
    timestamp = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    # Relationships
    trade = relationship("Trade", back_populates="orders")
    
    # Constraints
    __table_args__ = (
        CheckConstraint("side IN ('BUY', 'SELL')", name='ck_order_side'),
        Index('idx_orders_trade', 'trade_id'),
    )
    
    def __repr__(self):
        return f"<Order(trade={self.trade_id}, type={self.type}, status={self.status})>"

    @validates('side')
    def validate_side(self, key, side):
        if side not in ['BUY', 'SELL']:
            raise ValueError("Side must be 'BUY' or 'SELL'")
        return side


class Signal(Base):
    """Model for trading signals generated by analysis."""
    
    __tablename__ = 'signals'
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign keys
    asset_id = Column(UUID(as_uuid=True), ForeignKey('assets.id'), nullable=False)
    trade_id = Column(UUID(as_uuid=True), ForeignKey('trades.id'))
    
    # Signal data
    timestamp = Column(DateTime(timezone=True), nullable=False)
    signal_type = Column(String(10), nullable=False)  # 'BUY' or 'SELL'
    strength = Column(Numeric(5, 2))  # Signal strength 0-100
    rules_triggered = Column(ARRAY(Text))  # Which rules triggered the signal
    indicators_snapshot = Column(JSONB)  # Snapshot of indicators at signal time
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    
    # Relationships
    asset = relationship("Asset", back_populates="signals")
    trade = relationship("Trade", back_populates="signal")
    
    # Constraints
    __table_args__ = (
        CheckConstraint("signal_type IN ('BUY', 'SELL')", name='ck_signal_type'),
        Index('idx_signals_asset_time', 'asset_id', 'timestamp'),
    )
    
    def __repr__(self):
        return f"<Signal(asset={self.asset_id}, type={self.signal_type}, strength={self.strength})>"

    @validates('signal_type')
    def validate_signal_type(self, key, signal_type):
        if signal_type not in ['BUY', 'SELL']:
            raise ValueError("Signal type must be 'BUY' or 'SELL'")
        return signal_type


class SystemConfig(Base):
    """Model for system configuration key-value pairs."""
    
    __tablename__ = 'system_config'
    
    # Primary key
    key = Column(String(100), primary_key=True)
    
    # Config data
    value = Column(JSONB, nullable=False)
    description = Column(Text)
    
    # Timestamp
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    def __repr__(self):
        return f"<SystemConfig(key='{self.key}', description='{self.description}')>"

    @validates('key')
    def validate_key(self, key, config_key):
        if not config_key or len(config_key) > 100:
            raise ValueError("Config key must be non-empty and max 100 chars")
        return config_key.lower()