# utils/datetime_utils.py
"""Utilities for consistent timezone-aware datetime handling."""

from datetime import datetime, timezone
from typing import Optional


def utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime.
    
    This replaces datetime.utcnow() which returns timezone-naive datetime.
    All database operations expect timezone-aware datetimes.
    
    Returns:
        datetime: Current UTC time with timezone info
    """
    return datetime.now(timezone.utc)


def ensure_timezone_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure a datetime object is timezone-aware.
    
    Args:
        dt: Datetime object to check
        
    Returns:
        datetime: Timezone-aware datetime or None if input was None
    """
    if dt is None:
        return None
    
    if dt.tzinfo is None:
        # Assume UTC if no timezone info
        return dt.replace(tzinfo=timezone.utc)
    
    return dt


def safe_datetime_subtract(dt1: datetime, dt2: datetime) -> float:
    """Safely subtract two datetime objects, handling timezone awareness.
    
    Args:
        dt1: First datetime (typically current time)
        dt2: Second datetime (typically historical time)
        
    Returns:
        float: Difference in seconds (dt1 - dt2)
    """
    # Ensure both datetimes are timezone-aware
    dt1 = ensure_timezone_aware(dt1)
    dt2 = ensure_timezone_aware(dt2)
    
    if dt1 is None or dt2 is None:
        return 0.0
    
    return (dt1 - dt2).total_seconds()