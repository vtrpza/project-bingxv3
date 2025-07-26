"""
JSON utilities for handling serialization issues with Decimal and other types
"""

import json
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any, Dict, List, Union


def clean_for_json_serialization(data: Any) -> Any:
    """
    Recursively clean data to make it JSON serializable.
    Converts Decimal to float, datetime to ISO string, etc.
    """
    if data is None:
        return None
    elif isinstance(data, Decimal):
        return float(data)
    elif isinstance(data, datetime):
        return data.isoformat()
    elif isinstance(data, dict):
        return {key: clean_for_json_serialization(value) for key, value in data.items()}
    elif isinstance(data, (list, tuple)):
        return [clean_for_json_serialization(item) for item in data]
    elif isinstance(data, set):
        return list(clean_for_json_serialization(item) for item in data)
    else:
        return data


def safe_json_dumps(data: Any, **kwargs) -> str:
    """
    Safely serialize data to JSON string, cleaning problematic types first.
    """
    clean_data = clean_for_json_serialization(data)
    return json.dumps(clean_data, **kwargs)


def safe_json_loads(json_string: str) -> Any:
    """
    Safely deserialize JSON string to Python objects.
    """
    try:
        return json.loads(json_string)
    except (json.JSONDecodeError, TypeError) as e:
        raise ValueError(f"Failed to parse JSON: {e}")


class DecimalEncoder(json.JSONEncoder):
    """
    JSON encoder that handles Decimal objects by converting them to float.
    """
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)