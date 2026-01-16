"""
Centralized date/time utilities for ThrivePath project
Provides consistent timezone-aware datetime handling across the application
"""

from datetime import datetime, date, time, timezone
from typing import Optional, Union
import logging

logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================
# Project-wide date/time standards

# Default timezone for the application (UTC)
DEFAULT_TIMEZONE = timezone.utc

# ISO 8601 format strings
ISO_DATE_FORMAT = "%Y-%m-%d"
ISO_TIME_FORMAT = "%H:%M:%S"
ISO_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S"
ISO_DATETIME_TZ_FORMAT = "%Y-%m-%dT%H:%M:%S%z"

# ==================== CORE DATE UTILITIES ====================

def get_current_utc_datetime() -> datetime:
    """
    Get current UTC datetime with timezone awareness
    Replacement for datetime.utcnow() which is deprecated
    
    Returns:
        datetime: Current UTC datetime with timezone info
    """
    return datetime.now(timezone.utc)

def get_current_utc_date() -> date:
    """
    Get current UTC date
    
    Returns:
        date: Current UTC date
    """
    return get_current_utc_datetime().date()

def get_current_utc_time() -> time:
    """
    Get current UTC time
    
    Returns:
        time: Current UTC time
    """
    return get_current_utc_datetime().time()

def utc_now_iso() -> str:
    """
    Get current UTC datetime as ISO 8601 string with timezone
    Standard format for API responses and database storage
    
    Returns:
        str: ISO 8601 formatted datetime string (e.g., '2025-09-23T14:30:00+00:00')
    """
    return get_current_utc_datetime().isoformat()

def today_local_iso() -> str:
    """
    Get today's date in local timezone as ISO format (YYYY-MM-DD)
    Standard format for local date comparisons
    
    Returns:
        str: ISO date string in local timezone (e.g., '2025-09-23')
    """
    # Get current time in local timezone and extract date
    local_now = datetime.now()
    return local_now.date().isoformat()

# ==================== DATE PARSING UTILITIES ====================

def parse_date_string(date_str: str) -> Optional[date]:
    """
    Parse various date string formats to date object
    Handles ISO format and common variations
    
    Args:
        date_str: Date string to parse
        
    Returns:
        date: Parsed date object or None if parsing fails
    """
    if not date_str:
        return None
        
    try:
        # Try ISO format first (YYYY-MM-DD)
        if len(date_str) == 10 and date_str.count('-') == 2:
            return datetime.strptime(date_str, ISO_DATE_FORMAT).date()
            
        # Try parsing as datetime and extract date
        dt = parse_datetime_string(date_str)
        return dt.date() if dt else None
        
    except Exception as e:
        logger.warning(f"Failed to parse date string '{date_str}': {e}")
        return None

def parse_time_string(time_str: str) -> Optional[time]:
    """
    Parse various time string formats to time object
    Handles ISO format and common variations
    
    Args:
        time_str: Time string to parse
        
    Returns:
        time: Parsed time object or None if parsing fails
    """
    if not time_str:
        return None
        
    try:
        # Handle full datetime string - extract time part
        if 'T' in time_str:
            dt = parse_datetime_string(time_str)
            return dt.time() if dt else None
            
        # Handle time-only formats
        if len(time_str) == 8 and time_str.count(':') == 2:  # HH:MM:SS
            return datetime.strptime(time_str, ISO_TIME_FORMAT).time()
        elif len(time_str) == 5 and time_str.count(':') == 1:  # HH:MM
            return datetime.strptime(time_str, "%H:%M").time()
            
    except Exception as e:
        logger.warning(f"Failed to parse time string '{time_str}': {e}")
        
    return None

def parse_datetime_string(datetime_str: str) -> Optional[datetime]:
    """
    Parse various datetime string formats to timezone-aware datetime object
    Handles ISO format with and without timezone info
    
    Args:
        datetime_str: Datetime string to parse
        
    Returns:
        datetime: Parsed timezone-aware datetime object or None if parsing fails
    """
    if not datetime_str:
        return None
        
    try:
        # Handle timezone-aware ISO format
        if datetime_str.endswith('Z'):
            # Replace Z with +00:00 for proper parsing
            datetime_str = datetime_str[:-1] + '+00:00'
            
        if '+' in datetime_str or datetime_str.endswith('00:00'):
            return datetime.fromisoformat(datetime_str)
            
        # Handle timezone-naive ISO format - assume UTC
        if 'T' in datetime_str:
            dt_naive = datetime.fromisoformat(datetime_str)
            return dt_naive.replace(tzinfo=timezone.utc)
            
    except Exception as e:
        logger.warning(f"Failed to parse datetime string '{datetime_str}': {e}")
        
    return None

# ==================== DATE FORMATTING UTILITIES ====================

def format_date_iso(date_obj: Union[date, datetime]) -> str:
    """
    Format date or datetime object to ISO date string
    
    Args:
        date_obj: Date or datetime object to format
        
    Returns:
        str: ISO formatted date string (YYYY-MM-DD)
    """
    if isinstance(date_obj, datetime):
        return date_obj.date().isoformat()
    elif isinstance(date_obj, date):
        return date_obj.isoformat()
    else:
        raise ValueError(f"Expected date or datetime object, got {type(date_obj)}")

def format_time_iso(time_obj: Union[time, datetime]) -> str:
    """
    Format time or datetime object to ISO time string
    
    Args:
        time_obj: Time or datetime object to format
        
    Returns:
        str: ISO formatted time string (HH:MM:SS)
    """
    if isinstance(time_obj, datetime):
        return time_obj.time().isoformat()
    elif isinstance(time_obj, time):
        return time_obj.isoformat()
    else:
        raise ValueError(f"Expected time or datetime object, got {type(time_obj)}")

def format_datetime_iso(datetime_obj: datetime) -> str:
    """
    Format datetime object to ISO datetime string with timezone
    
    Args:
        datetime_obj: Datetime object to format
        
    Returns:
        str: ISO formatted datetime string with timezone
    """
    if not isinstance(datetime_obj, datetime):
        raise ValueError(f"Expected datetime object, got {type(datetime_obj)}")
        
    # Ensure timezone awareness
    if datetime_obj.tzinfo is None:
        datetime_obj = datetime_obj.replace(tzinfo=timezone.utc)
        
    return datetime_obj.isoformat()

# ==================== DATE COMPARISON UTILITIES ====================

def is_today(date_obj: Union[date, datetime, str]) -> bool:
    """
    Check if given date is today (in UTC)
    
    Args:
        date_obj: Date to check (date, datetime, or ISO string)
        
    Returns:
        bool: True if date is today, False otherwise
    """
    try:
        if isinstance(date_obj, str):
            date_obj = parse_date_string(date_obj)
            
        if isinstance(date_obj, datetime):
            date_obj = date_obj.date()
            
        if isinstance(date_obj, date):
            return date_obj == get_current_utc_date()
            
    except Exception as e:
        logger.warning(f"Error checking if date is today: {e}")
        
    return False

def is_same_date(date1: Union[date, datetime, str], date2: Union[date, datetime, str]) -> bool:
    """
    Check if two dates are the same
    
    Args:
        date1: First date to compare
        date2: Second date to compare
        
    Returns:
        bool: True if dates are the same, False otherwise
    """
    try:
        # Parse strings to date objects
        if isinstance(date1, str):
            date1 = parse_date_string(date1)
        if isinstance(date2, str):
            date2 = parse_date_string(date2)
            
        # Extract date from datetime objects
        if isinstance(date1, datetime):
            date1 = date1.date()
        if isinstance(date2, datetime):
            date2 = date2.date()
            
        return date1 == date2 if date1 and date2 else False
        
    except Exception as e:
        logger.warning(f"Error comparing dates: {e}")
        return False

# ==================== TIMEZONE UTILITIES ====================

def ensure_utc(datetime_obj: datetime) -> datetime:
    """
    Ensure datetime object is timezone-aware and in UTC
    
    Args:
        datetime_obj: Datetime object to convert
        
    Returns:
        datetime: Timezone-aware datetime in UTC
    """
    if datetime_obj.tzinfo is None:
        # Assume naive datetime is UTC
        return datetime_obj.replace(tzinfo=timezone.utc)
    else:
        # Convert to UTC if not already
        return datetime_obj.astimezone(timezone.utc)

def to_local_timezone(datetime_obj: datetime, target_tz: timezone = None) -> datetime:
    """
    Convert UTC datetime to local timezone
    
    Args:
        datetime_obj: UTC datetime to convert
        target_tz: Target timezone (defaults to system local)
        
    Returns:
        datetime: Datetime in target timezone
    """
    utc_dt = ensure_utc(datetime_obj)
    
    if target_tz:
        return utc_dt.astimezone(target_tz)
    else:
        # Convert to system local timezone
        return utc_dt.astimezone()

# ==================== DATABASE UTILITIES ====================

def prepare_date_for_db(date_obj: Union[date, datetime, str]) -> str:
    """
    Prepare date for database storage (ISO format)
    
    Args:
        date_obj: Date to prepare for database
        
    Returns:
        str: ISO formatted date string
    """
    if isinstance(date_obj, str):
        # Validate and reformat if needed
        parsed = parse_date_string(date_obj)
        return parsed.isoformat() if parsed else date_obj
    else:
        return format_date_iso(date_obj)

def prepare_datetime_for_db(datetime_obj: Union[datetime, str]) -> str:
    """
    Prepare datetime for database storage (ISO format with timezone)
    
    Args:
        datetime_obj: Datetime to prepare for database
        
    Returns:
        str: ISO formatted datetime string with timezone
    """
    if isinstance(datetime_obj, str):
        # Validate and reformat if needed
        parsed = parse_datetime_string(datetime_obj)
        return parsed.isoformat() if parsed else datetime_obj
    else:
        return format_datetime_iso(ensure_utc(datetime_obj))

# ==================== VALIDATION UTILITIES ====================

def validate_date_range(start_date: Union[date, str], end_date: Union[date, str]) -> bool:
    """
    Validate that start_date is before or equal to end_date
    
    Args:
        start_date: Start date to validate
        end_date: End date to validate
        
    Returns:
        bool: True if range is valid, False otherwise
    """
    try:
        if isinstance(start_date, str):
            start_date = parse_date_string(start_date)
        if isinstance(end_date, str):
            end_date = parse_date_string(end_date)
            
        return start_date <= end_date if start_date and end_date else False
        
    except Exception as e:
        logger.warning(f"Error validating date range: {e}")
        return False

def validate_time_range(start_time: Union[time, str], end_time: Union[time, str]) -> bool:
    """
    Validate that start_time is before end_time
    
    Args:
        start_time: Start time to validate
        end_time: End time to validate
        
    Returns:
        bool: True if range is valid, False otherwise
    """
    try:
        if isinstance(start_time, str):
            start_time = parse_time_string(start_time)
        if isinstance(end_time, str):
            end_time = parse_time_string(end_time)
            
        return start_time < end_time if start_time and end_time else False
        
    except Exception as e:
        logger.warning(f"Error validating time range: {e}")
        return False