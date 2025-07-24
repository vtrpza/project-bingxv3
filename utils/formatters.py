# utils/formatters.py
"""Data formatting utilities for BingX Trading Bot."""

from decimal import Decimal, ROUND_DOWN, ROUND_UP, ROUND_HALF_UP
from typing import Dict, Any, Optional, Union
from datetime import datetime, timezone
import json


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal objects."""
    
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class PriceFormatter:
    """Utilities for formatting prices and quantities."""
    
    @staticmethod
    def format_price(price: Union[Decimal, float, str], precision: int = 8) -> str:
        """Format price with specified precision."""
        if price is None:
            return "0.00000000"
        
        decimal_price = Decimal(str(price))
        format_str = f"{{:.{precision}f}}"
        return format_str.format(decimal_price)
    
    @staticmethod
    def format_percentage(value: Union[Decimal, float, str], precision: int = 2) -> str:
        """Format percentage value."""
        if value is None:
            return "0.00%"
        
        decimal_value = Decimal(str(value))
        format_str = f"{{:.{precision}f}}%"
        return format_str.format(decimal_value)
    
    @staticmethod
    def format_quantity(quantity: Union[Decimal, float, str], precision: int = 6) -> str:
        """Format quantity with specified precision."""
        if quantity is None:
            return "0.000000"
        
        decimal_quantity = Decimal(str(quantity))
        format_str = f"{{:.{precision}f}}"
        return format_str.format(decimal_quantity)
    
    @staticmethod
    def format_volume(volume: Union[Decimal, float, str]) -> str:
        """Format volume with automatic precision based on size."""
        if volume is None:
            return "0"
        
        decimal_volume = Decimal(str(volume))
        
        if decimal_volume >= 1000000:
            return f"{decimal_volume / 1000000:.2f}M"
        elif decimal_volume >= 1000:
            return f"{decimal_volume / 1000:.2f}K"
        else:
            return f"{decimal_volume:.2f}"
    
    @staticmethod
    def format_pnl(pnl: Union[Decimal, float, str]) -> str:
        """Format P&L with color indicators."""
        if pnl is None:
            return "0.00"
        
        decimal_pnl = Decimal(str(pnl))
        formatted = f"{decimal_pnl:.2f}"
        
        if decimal_pnl > 0:
            return f"+{formatted}"
        elif decimal_pnl < 0:
            return formatted  # Already has negative sign
        else:
            return "0.00"
    
    @staticmethod
    def round_to_precision(value: Union[Decimal, float, str], precision: int, 
                          rounding_mode: str = ROUND_HALF_UP) -> Decimal:
        """Round value to specified precision."""
        decimal_value = Decimal(str(value))
        precision_str = f"0.{'0' * precision}"
        return decimal_value.quantize(Decimal(precision_str), rounding=rounding_mode)
    
    @staticmethod
    def truncate_to_precision(value: Union[Decimal, float, str], precision: int) -> Decimal:
        """Truncate value to specified precision (always round down)."""
        return PriceFormatter.round_to_precision(value, precision, ROUND_DOWN)


class TimeFormatter:
    """Utilities for formatting time and dates."""
    
    @staticmethod
    def format_timestamp(timestamp: datetime, format_str: str = "%Y-%m-%d %H:%M:%S UTC") -> str:
        """Format timestamp with timezone handling."""
        if timestamp is None:
            return "N/A"
        
        # Ensure UTC timezone
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        elif timestamp.tzinfo != timezone.utc:
            timestamp = timestamp.astimezone(timezone.utc)
        
        return timestamp.strftime(format_str)
    
    @staticmethod
    def format_duration(start_time: datetime, end_time: datetime = None) -> str:
        """Format duration between two timestamps."""
        if start_time is None:
            return "N/A"
        
        if end_time is None:
            from utils.datetime_utils import utc_now
            end_time = utc_now()
        
        # Ensure both timestamps have timezone info
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)
        
        duration = end_time - start_time
        
        total_seconds = int(duration.total_seconds())
        
        if total_seconds < 60:
            return f"{total_seconds}s"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            return f"{minutes}m {seconds}s"
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours}h {minutes}m"
        else:
            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            return f"{days}d {hours}h"
    
    @staticmethod
    def format_relative_time(timestamp: datetime) -> str:
        """Format timestamp relative to now (e.g., '2 minutes ago')."""
        if timestamp is None:
            return "N/A"
        
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        
        diff = now - timestamp
        total_seconds = int(diff.total_seconds())
        
        if total_seconds < 0:
            return "in the future"
        elif total_seconds < 60:
            return f"{total_seconds} seconds ago"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        else:
            days = total_seconds // 86400
            return f"{days} day{'s' if days != 1 else ''} ago"


class DataFormatter:
    """General data formatting utilities."""
    
    @staticmethod
    def format_trade_summary(trade_data: Dict[str, Any]) -> Dict[str, str]:
        """Format trade data for display."""
        return {
            "symbol": trade_data.get("symbol", "N/A"),
            "side": trade_data.get("side", "N/A"),
            "entry_price": PriceFormatter.format_price(trade_data.get("entry_price")),
            "quantity": PriceFormatter.format_quantity(trade_data.get("quantity")),
            "stop_loss": PriceFormatter.format_price(trade_data.get("stop_loss")) if trade_data.get("stop_loss") else "N/A",
            "take_profit": PriceFormatter.format_price(trade_data.get("take_profit")) if trade_data.get("take_profit") else "N/A",
            "status": trade_data.get("status", "N/A"),
            "entry_time": TimeFormatter.format_timestamp(trade_data.get("entry_time")) if trade_data.get("entry_time") else "N/A",
            "pnl": PriceFormatter.format_pnl(trade_data.get("pnl")) if trade_data.get("pnl") else "0.00",
        }
    
    @staticmethod
    def format_signal_summary(signal_data: Dict[str, Any]) -> Dict[str, str]:
        """Format signal data for display."""
        return {
            "symbol": signal_data.get("symbol", "N/A"),
            "type": signal_data.get("signal_type", "N/A"),
            "strength": PriceFormatter.format_percentage(signal_data.get("strength", 0) * 100),
            "rules": ", ".join(signal_data.get("rules_triggered", [])),
            "timestamp": TimeFormatter.format_timestamp(signal_data.get("timestamp")) if signal_data.get("timestamp") else "N/A",
        }
    
    @staticmethod
    def format_market_data(candle_data: Dict[str, Any]) -> Dict[str, str]:
        """Format market data for display."""
        return {
            "timestamp": TimeFormatter.format_timestamp(candle_data.get("timestamp")) if candle_data.get("timestamp") else "N/A",
            "timeframe": candle_data.get("timeframe", "N/A"),
            "open": PriceFormatter.format_price(candle_data.get("open")),
            "high": PriceFormatter.format_price(candle_data.get("high")),
            "low": PriceFormatter.format_price(candle_data.get("low")),
            "close": PriceFormatter.format_price(candle_data.get("close")),
            "volume": PriceFormatter.format_volume(candle_data.get("volume")),
        }
    
    @staticmethod
    def format_indicators(indicator_data: Dict[str, Any]) -> Dict[str, str]:
        """Format technical indicators for display."""
        return {
            "timestamp": TimeFormatter.format_timestamp(indicator_data.get("timestamp")) if indicator_data.get("timestamp") else "N/A",
            "timeframe": indicator_data.get("timeframe", "N/A"),
            "mm1": PriceFormatter.format_price(indicator_data.get("mm1")) if indicator_data.get("mm1") else "N/A",
            "center": PriceFormatter.format_price(indicator_data.get("center")) if indicator_data.get("center") else "N/A",
            "rsi": PriceFormatter.format_price(indicator_data.get("rsi"), 2) if indicator_data.get("rsi") else "N/A",
            "volume_sma": PriceFormatter.format_volume(indicator_data.get("volume_sma")) if indicator_data.get("volume_sma") else "N/A",
        }
    
    @staticmethod
    def format_performance_stats(stats: Dict[str, Any]) -> Dict[str, str]:
        """Format performance statistics for display."""
        total_trades = stats.get("total_trades", 0)
        winning_trades = stats.get("winning_trades", 0)
        
        return {
            "total_trades": str(total_trades),
            "winning_trades": str(winning_trades),
            "losing_trades": str(stats.get("losing_trades", 0)),
            "win_rate": PriceFormatter.format_percentage(stats.get("win_rate", 0)),
            "total_pnl": PriceFormatter.format_pnl(stats.get("total_pnl", 0)),
            "avg_pnl": PriceFormatter.format_pnl(stats.get("avg_pnl", 0)),
            "max_win": PriceFormatter.format_pnl(stats.get("max_win", 0)),
            "max_loss": PriceFormatter.format_pnl(stats.get("max_loss", 0)),
        }
    
    @staticmethod
    def to_json(data: Any, indent: int = None) -> str:
        """Convert data to JSON string with custom encoder."""
        return json.dumps(data, cls=DecimalEncoder, indent=indent, ensure_ascii=False)
    
    @staticmethod
    def from_json(json_str: str) -> Any:
        """Parse JSON string to Python object."""
        return json.loads(json_str)


class TableFormatter:
    """Utilities for formatting data in tabular format."""
    
    @staticmethod
    def format_table(data: list, headers: list, max_width: int = 20) -> str:
        """Format data as a simple ASCII table."""
        if not data or not headers:
            return ""
        
        # Calculate column widths
        col_widths = []
        for i, header in enumerate(headers):
            max_width_col = len(header)
            for row in data:
                if i < len(row):
                    max_width_col = max(max_width_col, len(str(row[i])))
            col_widths.append(min(max_width_col, max_width))
        
        # Format header
        header_row = " | ".join(header.ljust(col_widths[i]) for i, header in enumerate(headers))
        separator = "-" * len(header_row)
        
        # Format data rows
        formatted_rows = []
        for row in data:
            formatted_row = " | ".join(
                str(row[i]).ljust(col_widths[i])[:col_widths[i]] if i < len(row) else "".ljust(col_widths[i])
                for i in range(len(headers))
            )
            formatted_rows.append(formatted_row)
        
        return "\n".join([header_row, separator] + formatted_rows)
    
    @staticmethod
    def format_key_value_pairs(data: Dict[str, str], key_width: int = 20) -> str:
        """Format key-value pairs in aligned columns."""
        if not data:
            return ""
        
        formatted_lines = []
        for key, value in data.items():
            formatted_key = key.ljust(key_width)
            formatted_lines.append(f"{formatted_key}: {value}")
        
        return "\n".join(formatted_lines)