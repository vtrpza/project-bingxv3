# config/trading_config.py
"""Trading strategy and risk management configuration."""

import os
from decimal import Decimal
from typing import List, Dict, Any
from dataclasses import dataclass


@dataclass
class TrailingStopLevel:
    """Configuration for trailing stop levels."""
    trigger: Decimal  # Profit percentage to trigger this level
    stop: Decimal     # Stop loss percentage for this level


class TradingConfig:
    """Trading strategy and risk management parameters."""
    
    # Position Sizing & Limits
    MAX_CONCURRENT_TRADES: int = int(os.getenv("MAX_CONCURRENT_TRADES", "5"))
    MIN_ORDER_SIZE_USDT: Decimal = Decimal(os.getenv("MIN_ORDER_SIZE_USDT", "10.0"))
    MAX_POSITION_SIZE_PERCENT: Decimal = Decimal(os.getenv("MAX_POSITION_SIZE_PERCENT", "2.0"))  # % of total balance
    
    # Risk Management
    INITIAL_STOP_LOSS_PERCENT: Decimal = Decimal(os.getenv("INITIAL_STOP_LOSS_PERCENT", "0.02"))  # 2%
    BREAKEVEN_TRIGGER_PERCENT: Decimal = Decimal(os.getenv("BREAKEVEN_TRIGGER_PERCENT", "0.015"))  # 1.5%
    MAX_DAILY_LOSS_PERCENT: Decimal = Decimal(os.getenv("MAX_DAILY_LOSS_PERCENT", "5.0"))  # 5%
    MAX_DRAWDOWN_PERCENT: Decimal = Decimal(os.getenv("MAX_DRAWDOWN_PERCENT", "10.0"))  # 10%
    
    # Trailing Stop Configuration
    TRAILING_STOP_LEVELS: List[TrailingStopLevel] = [
        TrailingStopLevel(trigger=Decimal("0.015"), stop=Decimal("0.0")),    # 1.5% → Breakeven
        TrailingStopLevel(trigger=Decimal("0.03"), stop=Decimal("0.015")),   # 3% → SL +1.5%
        TrailingStopLevel(trigger=Decimal("0.05"), stop=Decimal("0.03")),    # 5% → SL +3%
        TrailingStopLevel(trigger=Decimal("0.08"), stop=Decimal("0.05")),    # 8% → SL +5%
        TrailingStopLevel(trigger=Decimal("0.10"), stop=Decimal("0.08")),    # 10% → SL +8%
        TrailingStopLevel(trigger=Decimal("0.15"), stop=Decimal("0.10")),    # 15% → SL +10%
        TrailingStopLevel(trigger=Decimal("0.20"), stop=Decimal("0.15")),    # 20% → SL +15%
    ]
    
    # Take Profit Levels
    TAKE_PROFIT_LEVELS: List[Dict[str, Any]] = [
        {"percentage": Decimal("0.03"), "size_percent": 25},  # 3% profit, close 25%
        {"percentage": Decimal("0.05"), "size_percent": 25},  # 5% profit, close 25%
        {"percentage": Decimal("0.08"), "size_percent": 25},  # 8% profit, close 25%
        {"percentage": Decimal("0.12"), "size_percent": 25},  # 12% profit, close 25%
    ]
    
    # Technical Indicators Configuration
    MM1_PERIOD: int = int(os.getenv("MM1_PERIOD", "9"))      # Fast EMA period
    CENTER_PERIOD: int = int(os.getenv("CENTER_PERIOD", "21"))  # Slow EMA period
    RSI_PERIOD: int = int(os.getenv("RSI_PERIOD", "14"))     # RSI period
    VOLUME_SMA_PERIOD: int = int(os.getenv("VOLUME_SMA_PERIOD", "20"))  # Volume SMA period
    
    # Trading Rules Parameters
    RSI_MIN: Decimal = Decimal(os.getenv("RSI_MIN", "35"))   # Minimum RSI for entry (Rule 1)
    RSI_MAX: Decimal = Decimal(os.getenv("RSI_MAX", "73"))   # Maximum RSI for entry (Rule 1)
    
    # Moving Average Distance Rules
    MA_DISTANCE_2H_PERCENT: Decimal = Decimal(os.getenv("MA_DISTANCE_2H_PERCENT", "0.02"))  # 2% for 2h timeframe
    MA_DISTANCE_4H_PERCENT: Decimal = Decimal(os.getenv("MA_DISTANCE_4H_PERCENT", "0.03"))  # 3% for 4h timeframe
    
    # Volume Spike Detection
    VOLUME_SPIKE_THRESHOLD: Decimal = Decimal(os.getenv("VOLUME_SPIKE_THRESHOLD", "2.0"))  # 2x average volume
    VOLUME_SPIKE_LOOKBACK: int = int(os.getenv("VOLUME_SPIKE_LOOKBACK", "20"))  # Periods to look back for average
    
    # Scanner Configuration
    SCAN_INTERVAL_SECONDS: int = int(os.getenv("SCAN_INTERVAL_SECONDS", "30"))
    MIN_VOLUME_24H_USDT: Decimal = Decimal(os.getenv("MIN_VOLUME_24H_USDT", "10000"))  # Minimum 24h volume - reduced for perpetuals
    MAX_ASSETS_TO_SCAN: int = int(os.getenv("MAX_ASSETS_TO_SCAN", "100"))
    
    # Timeframes Configuration
    ANALYSIS_TIMEFRAMES: List[str] = os.getenv("ANALYSIS_TIMEFRAMES", "2h,4h").split(",")
    SPOT_TIMEFRAME: str = os.getenv("SPOT_TIMEFRAME", "1m")
    
    # Signal Strength Weights
    RULE_WEIGHTS: Dict[str, Decimal] = {
        "ma_crossover": Decimal("0.4"),     # Rule 1: MA crossover with RSI
        "ma_distance": Decimal("0.3"),      # Rule 2: MA distance
        "volume_spike": Decimal("0.3"),     # Rule 3: Volume spike
    }
    
    # Signal Confidence Thresholds
    SIGNAL_THRESHOLDS: Dict[str, Decimal] = {
        "strong_buy": Decimal("0.8"),       # >= 80% confidence
        "buy": Decimal("0.6"),              # >= 60% confidence
        "neutral": Decimal("0.4"),          # 40-60% confidence
        "sell": Decimal("0.6"),             # >= 60% confidence (sell)
        "strong_sell": Decimal("0.8"),      # >= 80% confidence (sell)
    }
    
    # Order Execution Configuration
    ORDER_TIMEOUT_SECONDS: int = int(os.getenv("ORDER_TIMEOUT_SECONDS", "60"))
    ORDER_RETRY_ATTEMPTS: int = int(os.getenv("ORDER_RETRY_ATTEMPTS", "3"))
    ORDER_RETRY_DELAY: float = float(os.getenv("ORDER_RETRY_DELAY", "1.0"))
    
    # Slippage Protection
    MAX_SLIPPAGE_PERCENT: Decimal = Decimal(os.getenv("MAX_SLIPPAGE_PERCENT", "0.5"))  # 0.5%
    
    # Emergency Controls
    EMERGENCY_STOP: bool = os.getenv("EMERGENCY_STOP", "False").lower() == "true"
    TRADING_ENABLED: bool = os.getenv("TRADING_ENABLED", "True").lower() == "true"
    PAPER_TRADING: bool = os.getenv("PAPER_TRADING", "False").lower() == "true"
    
    @classmethod
    def get_trailing_stop_level(cls, profit_percent: Decimal) -> TrailingStopLevel:
        """Get appropriate trailing stop level based on current profit."""
        # Find the highest level that has been triggered
        triggered_level = None
        for level in cls.TRAILING_STOP_LEVELS:
            if profit_percent >= level.trigger:
                triggered_level = level
            else:
                break
        
        return triggered_level or TrailingStopLevel(trigger=Decimal("0"), stop=cls.INITIAL_STOP_LOSS_PERCENT)
    
    @classmethod
    def calculate_position_size(cls, balance: Decimal, price: Decimal) -> Decimal:
        """Calculate position size based on risk management."""
        max_position_value = balance * (cls.MAX_POSITION_SIZE_PERCENT / 100)
        max_quantity = max_position_value / price
        
        # Ensure minimum order size
        min_quantity = cls.MIN_ORDER_SIZE_USDT / price
        
        return max(min_quantity, max_quantity)
    
    @classmethod
    def is_rsi_in_range(cls, rsi: Decimal) -> bool:
        """Check if RSI is within acceptable range for Rule 1."""
        return cls.RSI_MIN <= rsi <= cls.RSI_MAX
    
    @classmethod
    def get_ma_distance_threshold(cls, timeframe: str) -> Decimal:
        """Get MA distance threshold for specific timeframe."""
        if timeframe == "2h":
            return cls.MA_DISTANCE_2H_PERCENT
        elif timeframe == "4h":
            return cls.MA_DISTANCE_4H_PERCENT
        else:
            return cls.MA_DISTANCE_2H_PERCENT  # Default
    
    @classmethod
    def is_volume_spike(cls, current_volume: Decimal, average_volume: Decimal) -> bool:
        """Check if current volume represents a spike."""
        if average_volume <= 0:
            return False
        return current_volume >= (average_volume * cls.VOLUME_SPIKE_THRESHOLD)
    
    @classmethod
    def calculate_signal_strength(cls, rules_triggered: List[str]) -> Decimal:
        """Calculate overall signal strength based on triggered rules."""
        total_weight = Decimal("0")
        for rule in rules_triggered:
            if rule in cls.RULE_WEIGHTS:
                total_weight += cls.RULE_WEIGHTS[rule]
        return min(total_weight, Decimal("1.0"))  # Cap at 1.0
    
    @classmethod
    def get_signal_type(cls, strength: Decimal, direction: str) -> str:
        """Get signal type based on strength and direction."""
        if direction.upper() == "BUY":
            if strength >= cls.SIGNAL_THRESHOLDS["strong_buy"]:
                return "STRONG_BUY"
            elif strength >= cls.SIGNAL_THRESHOLDS["buy"]:
                return "BUY"
        elif direction.upper() == "SELL":
            if strength >= cls.SIGNAL_THRESHOLDS["strong_sell"]:
                return "STRONG_SELL"
            elif strength >= cls.SIGNAL_THRESHOLDS["sell"]:
                return "SELL"
        
        return "NEUTRAL"
    
    @classmethod
    def validate(cls) -> List[str]:
        """Validate trading configuration."""
        errors = []
        
        # Validate numeric ranges
        if cls.MAX_CONCURRENT_TRADES < 1:
            errors.append("MAX_CONCURRENT_TRADES must be at least 1")
        
        if cls.MIN_ORDER_SIZE_USDT <= 0:
            errors.append("MIN_ORDER_SIZE_USDT must be positive")
        
        if cls.MAX_POSITION_SIZE_PERCENT <= 0 or cls.MAX_POSITION_SIZE_PERCENT > 100:
            errors.append("MAX_POSITION_SIZE_PERCENT must be between 0 and 100")
        
        if cls.INITIAL_STOP_LOSS_PERCENT < 0 or cls.INITIAL_STOP_LOSS_PERCENT > 0.2:
            errors.append("INITIAL_STOP_LOSS_PERCENT must be between 0 and 0.2 (20%)")
        
        if cls.RSI_MIN < 0 or cls.RSI_MIN > 100:
            errors.append("RSI_MIN must be between 0 and 100")
        
        if cls.RSI_MAX < 0 or cls.RSI_MAX > 100:
            errors.append("RSI_MAX must be between 0 and 100")
        
        if cls.RSI_MIN >= cls.RSI_MAX:
            errors.append("RSI_MIN must be less than RSI_MAX")
        
        # Validate indicator periods
        if cls.MM1_PERIOD < 1:
            errors.append("MM1_PERIOD must be at least 1")
        
        if cls.CENTER_PERIOD < 1:
            errors.append("CENTER_PERIOD must be at least 1")
        
        if cls.RSI_PERIOD < 1:
            errors.append("RSI_PERIOD must be at least 1")
        
        # Validate trailing stop levels are in ascending order
        for i, level in enumerate(cls.TRAILING_STOP_LEVELS[1:], 1):
            prev_level = cls.TRAILING_STOP_LEVELS[i-1]
            if level.trigger <= prev_level.trigger:
                errors.append("TRAILING_STOP_LEVELS must be in ascending order by trigger")
                break
        
        # Validate timeframes
        valid_timeframes = ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "12h", "1d"]
        for tf in cls.ANALYSIS_TIMEFRAMES:
            if tf not in valid_timeframes:
                errors.append(f"Invalid timeframe: {tf}. Valid options: {valid_timeframes}")
        
        return errors
    
    @classmethod
    def get_info(cls) -> Dict[str, Any]:
        """Get trading configuration summary."""
        return {
            "max_concurrent_trades": cls.MAX_CONCURRENT_TRADES,
            "min_order_size": float(cls.MIN_ORDER_SIZE_USDT),
            "max_position_percent": float(cls.MAX_POSITION_SIZE_PERCENT),
            "initial_stop_loss": float(cls.INITIAL_STOP_LOSS_PERCENT),
            "rsi_range": [float(cls.RSI_MIN), float(cls.RSI_MAX)],
            "analysis_timeframes": cls.ANALYSIS_TIMEFRAMES,
            "trading_enabled": cls.TRADING_ENABLED,
            "paper_trading": cls.PAPER_TRADING,
            "emergency_stop": cls.EMERGENCY_STOP,
        }