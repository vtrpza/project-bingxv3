# trading/__init__.py
"""Trading module for BingX trading bot."""

from .engine import TradingEngine, TradingEngineError
from .order_manager import OrderManager, OrderManagerError, OrderType, OrderStatus
from .risk_manager import RiskManager, RiskManagerError, RiskMetrics
from .position_tracker import PositionTracker, PositionTrackerError, PositionData, PortfolioMetrics
# Note: TradingWorker is not imported to avoid module execution conflicts when running as -m trading.worker

__all__ = [
    # Main components
    'TradingEngine',
    'OrderManager', 
    'RiskManager',
    'PositionTracker',
    
    # Exceptions
    'TradingEngineError',
    'OrderManagerError',
    'RiskManagerError', 
    'PositionTrackerError',
    
    # Enums and data classes
    'OrderType',
    'OrderStatus',
    'RiskMetrics',
    'PositionData',
    'PortfolioMetrics',
]

# Version info
__version__ = '1.0.0'
__author__ = 'BingX Trading Bot'
__description__ = 'Complete trading engine for BingX cryptocurrency exchange'