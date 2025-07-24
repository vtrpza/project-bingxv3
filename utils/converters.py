# utils/converters.py
"""Utility functions for data type conversion."""

import json
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Union


def convert_decimals(obj: Any) -> Any:
    """
    Recursively convert Decimal objects to float for JSON serialization.
    
    Args:
        obj: Object that may contain Decimal values
        
    Returns:
        Object with Decimals converted to floats
    """
    if isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals(v) for v in obj]
    elif isinstance(obj, tuple):
        return tuple(convert_decimals(v) for v in obj)
    elif isinstance(obj, Decimal):
        return float(obj)
    else:
        return obj


def safe_json_dumps(obj: Any, **kwargs) -> str:
    """
    Safely serialize object to JSON, converting Decimals to floats.
    
    Args:
        obj: Object to serialize
        **kwargs: Additional arguments for json.dumps
        
    Returns:
        JSON string
    """
    converted_obj = convert_decimals(obj)
    return json.dumps(converted_obj, **kwargs)


def safe_decimal_conversion(value: Any, default: Decimal = Decimal('0')) -> Decimal:
    """
    Safely convert value to Decimal.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        Decimal value
    """
    if isinstance(value, Decimal):
        return value
    
    try:
        if value is None:
            return default
        return Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        return default