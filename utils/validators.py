# utils/validators.py
"""Data validation utilities for BingX Trading Bot."""

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Union
from datetime import datetime


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass


class Validator:
    """General purpose data validator."""
    
    @staticmethod
    def is_valid_symbol(symbol: str) -> bool:
        """Validate cryptocurrency trading symbol format with strict filtering."""
        if not symbol or not isinstance(symbol, str):
            return False
        
        # Convert to uppercase for validation
        symbol = symbol.upper().strip()
        
        # Reject symbols with invalid characters immediately
        invalid_patterns = [
            r'^\$',           # Starts with $ (like $1/USDT)
            r'[^A-Z0-9/]',    # Contains non-alphanumeric chars except /
            r'/.*/',          # Multiple slashes
            r'^/',            # Starts with slash
            r'/$',            # Ends with slash
            r'^[0-9]+/',      # Starts with numbers only (like 1/USDT)
            r'/[0-9]+$',      # Ends with numbers only
        ]
        
        for pattern in invalid_patterns:
            if re.search(pattern, symbol):
                return False
        
        # Expected format: BASE/QUOTE (e.g., BTC/USDT)
        # Base must be 2-10 chars, Quote must be 3-5 chars
        # Base cannot be purely numeric
        pattern = r'^[A-Z][A-Z0-9]{1,9}\/[A-Z]{3,5}$'
        if not re.match(pattern, symbol):
            return False
        
        # Additional validation: base cannot be purely numeric
        base_part = symbol.split('/')[0]
        if base_part.isdigit():
            return False
        
        # Reject known invalid symbols
        invalid_symbols = {
            '$1/USDT', '1/USDT', '2/USDT', '0/USDT', 
            'NULL/USDT', 'UNDEFINED/USDT', 'TEST/USDT'
        }
        if symbol in invalid_symbols:
            return False
        
        return True
    
    @staticmethod
    def is_valid_side(side: str) -> bool:
        """Validate trading side."""
        return side and side.upper() in ['BUY', 'SELL']
    
    @staticmethod
    def is_valid_decimal(value: Any, min_value: Decimal = None, max_value: Decimal = None) -> bool:
        """Validate decimal value with optional range check."""
        try:
            decimal_value = Decimal(str(value))
            
            if min_value is not None and decimal_value < min_value:
                return False
            
            if max_value is not None and decimal_value > max_value:
                return False
            
            return True
        except (InvalidOperation, ValueError, TypeError):
            return False
    
    @staticmethod
    def is_valid_percentage(value: Any) -> bool:
        """Validate percentage value (0-100)."""
        return Validator.is_valid_decimal(value, Decimal('0'), Decimal('100'))
    
    @staticmethod
    def is_valid_price(price: Any) -> bool:
        """Validate price value (must be positive)."""
        return Validator.is_valid_decimal(price, Decimal('0'))
    
    @staticmethod
    def is_valid_quantity(quantity: Any) -> bool:
        """Validate quantity value (must be positive)."""
        return Validator.is_valid_decimal(quantity, Decimal('0'))
    
    @staticmethod
    def is_valid_rsi(rsi: Any) -> bool:
        """Validate RSI value (0-100)."""
        return Validator.is_valid_decimal(rsi, Decimal('0'), Decimal('100'))
    
    @staticmethod
    def is_valid_timeframe(timeframe: str) -> bool:
        """Validate timeframe format."""
        if not timeframe or not isinstance(timeframe, str):
            return False
        
        valid_timeframes = [
            'spot', '1m', '3m', '5m', '15m', '30m', 
            '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w'
        ]
        return timeframe.lower() in valid_timeframes
    
    @staticmethod
    def is_valid_timestamp(timestamp: Any) -> bool:
        """Validate timestamp value."""
        if isinstance(timestamp, datetime):
            return True
        
        if isinstance(timestamp, (int, float)):
            try:
                datetime.fromtimestamp(timestamp)
                return True
            except (ValueError, OverflowError):
                return False
        
        if isinstance(timestamp, str):
            try:
                datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return True
            except ValueError:
                return False
        
        return False
    
    @staticmethod
    def is_valid_uuid(uuid_string: str) -> bool:
        """Validate UUID format."""
        if not uuid_string or not isinstance(uuid_string, str):
            return False
        
        pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        return bool(re.match(pattern, uuid_string.lower()))


class TradingValidator:
    """Validator for trading-specific data."""
    
    @staticmethod
    def validate_trade_data(data: Dict[str, Any]) -> Dict[str, str]:
        """Validate trade creation data."""
        errors = {}
        
        # Required fields
        required_fields = ['symbol', 'side', 'entry_price', 'quantity']
        for field in required_fields:
            if field not in data or data[field] is None:
                errors[field] = f"{field} is required"
        
        # Validate symbol
        if 'symbol' in data and not Validator.is_valid_symbol(data['symbol']):
            errors['symbol'] = "Invalid symbol format"
        
        # Validate side
        if 'side' in data and not Validator.is_valid_side(data['side']):
            errors['side'] = "Side must be 'BUY' or 'SELL'"
        
        # Validate prices
        if 'entry_price' in data and not Validator.is_valid_price(data['entry_price']):
            errors['entry_price'] = "Entry price must be positive"
        
        if 'stop_loss' in data and data['stop_loss'] is not None:
            if not Validator.is_valid_price(data['stop_loss']):
                errors['stop_loss'] = "Stop loss must be positive"
        
        if 'take_profit' in data and data['take_profit'] is not None:
            if not Validator.is_valid_price(data['take_profit']):
                errors['take_profit'] = "Take profit must be positive"
        
        # Validate quantity
        if 'quantity' in data and not Validator.is_valid_quantity(data['quantity']):
            errors['quantity'] = "Quantity must be positive"
        
        return errors
    
    @staticmethod
    def validate_order_data(data: Dict[str, Any]) -> Dict[str, str]:
        """Validate order data."""
        errors = {}
        
        required_fields = ['type', 'side', 'quantity']
        for field in required_fields:
            if field not in data or data[field] is None:
                errors[field] = f"{field} is required"
        
        # Validate order type
        valid_types = ['MARKET', 'LIMIT', 'STOP_LOSS', 'TAKE_PROFIT']
        if 'type' in data and data['type'] not in valid_types:
            errors['type'] = f"Order type must be one of: {valid_types}"
        
        # Validate side
        if 'side' in data and not Validator.is_valid_side(data['side']):
            errors['side'] = "Side must be 'BUY' or 'SELL'"
        
        # Validate quantity
        if 'quantity' in data and not Validator.is_valid_quantity(data['quantity']):
            errors['quantity'] = "Quantity must be positive"
        
        # Validate price for limit orders
        if data.get('type') == 'LIMIT':
            if 'price' not in data or not Validator.is_valid_price(data['price']):
                errors['price'] = "Price is required for limit orders and must be positive"
        
        return errors
    
    @staticmethod
    def validate_signal_data(data: Dict[str, Any]) -> Dict[str, str]:
        """Validate signal data."""
        errors = {}
        
        required_fields = ['symbol', 'signal_type', 'strength']
        for field in required_fields:
            if field not in data or data[field] is None:
                errors[field] = f"{field} is required"
        
        # Validate symbol
        if 'symbol' in data and not Validator.is_valid_symbol(data['symbol']):
            errors['symbol'] = "Invalid symbol format"
        
        # Validate signal type
        if 'signal_type' in data and not Validator.is_valid_side(data['signal_type']):
            errors['signal_type'] = "Signal type must be 'BUY' or 'SELL'"
        
        # Validate strength (0-1)
        if 'strength' in data:
            if not Validator.is_valid_decimal(data['strength'], Decimal('0'), Decimal('1')):
                errors['strength'] = "Signal strength must be between 0 and 1"
        
        # Validate rules triggered
        if 'rules_triggered' in data:
            if not isinstance(data['rules_triggered'], list):
                errors['rules_triggered'] = "Rules triggered must be a list"
        
        return errors


class MarketDataValidator:
    """Validator for market data."""
    
    @staticmethod
    def validate_candle_data(data: Dict[str, Any]) -> Dict[str, str]:
        """Validate OHLCV candle data."""
        errors = {}
        
        required_fields = ['timestamp', 'timeframe', 'open', 'high', 'low', 'close', 'volume']
        for field in required_fields:
            if field not in data or data[field] is None:
                errors[field] = f"{field} is required"
        
        # Validate timestamp
        if 'timestamp' in data and not Validator.is_valid_timestamp(data['timestamp']):
            errors['timestamp'] = "Invalid timestamp format"
        
        # Validate timeframe
        if 'timeframe' in data and not Validator.is_valid_timeframe(data['timeframe']):
            errors['timeframe'] = "Invalid timeframe"
        
        # Validate OHLCV values
        price_fields = ['open', 'high', 'low', 'close']
        for field in price_fields:
            if field in data and not Validator.is_valid_price(data[field]):
                errors[field] = f"{field} must be positive"
        
        if 'volume' in data and not Validator.is_valid_quantity(data['volume']):
            errors['volume'] = "Volume must be positive"
        
        # Validate OHLC relationships
        if all(field in data for field in price_fields):
            try:
                open_price = Decimal(str(data['open']))
                high_price = Decimal(str(data['high']))
                low_price = Decimal(str(data['low']))
                close_price = Decimal(str(data['close']))
                
                if low_price > high_price:
                    errors['price_range'] = "Low price cannot be higher than high price"
                
                if open_price < low_price or open_price > high_price:
                    errors['open_price'] = "Open price must be within low-high range"
                
                if close_price < low_price or close_price > high_price:
                    errors['close_price'] = "Close price must be within low-high range"
                    
            except (InvalidOperation, ValueError):
                pass  # Price validation already handled above
        
        return errors
    
    @staticmethod
    def validate_indicator_data(data: Dict[str, Any]) -> Dict[str, str]:
        """Validate technical indicator data."""
        errors = {}
        
        required_fields = ['timestamp', 'timeframe']
        for field in required_fields:
            if field not in data or data[field] is None:
                errors[field] = f"{field} is required"
        
        # Validate timestamp
        if 'timestamp' in data and not Validator.is_valid_timestamp(data['timestamp']):
            errors['timestamp'] = "Invalid timestamp format"
        
        # Validate timeframe
        if 'timeframe' in data and not Validator.is_valid_timeframe(data['timeframe']):
            errors['timeframe'] = "Invalid timeframe"
        
        # Validate optional indicator values
        if 'mm1' in data and data['mm1'] is not None:
            if not Validator.is_valid_decimal(data['mm1']):
                errors['mm1'] = "MM1 must be a valid decimal"
        
        if 'center' in data and data['center'] is not None:
            if not Validator.is_valid_decimal(data['center']):
                errors['center'] = "Center must be a valid decimal"
        
        if 'rsi' in data and data['rsi'] is not None:
            if not Validator.is_valid_rsi(data['rsi']):
                errors['rsi'] = "RSI must be between 0 and 100"
        
        if 'volume_sma' in data and data['volume_sma'] is not None:
            if not Validator.is_valid_decimal(data['volume_sma']):
                errors['volume_sma'] = "Volume SMA must be a valid decimal"
        
        return errors


def validate_and_raise(data: Dict[str, Any], validator_func) -> None:
    """Validate data and raise ValidationError if invalid."""
    errors = validator_func(data)
    if errors:
        error_messages = [f"{field}: {message}" for field, message in errors.items()]
        raise ValidationError("; ".join(error_messages))


def sanitize_symbol(symbol: str) -> str:
    """Sanitize and normalize trading symbol."""
    if not symbol:
        return ""
    
    # Convert to uppercase and remove whitespace
    symbol = symbol.strip().upper()
    
    # Add slash if missing (e.g., BTCUSDT -> BTC/USDT)
    if '/' not in symbol and len(symbol) >= 6:
        # Assume last 3-4 chars are quote currency
        if symbol.endswith('USDT'):
            base = symbol[:-4]
            quote = symbol[-4:]
        elif symbol.endswith('BTC') or symbol.endswith('ETH') or symbol.endswith('BNB'):
            base = symbol[:-3]
            quote = symbol[-3:]
        else:
            return symbol  # Can't determine split
        
        symbol = f"{base}/{quote}"
    
    return symbol


def sanitize_decimal(value: Any, default: Decimal = None) -> Optional[Decimal]:
    """Sanitize value to Decimal with error handling."""
    if value is None:
        return default
    
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default