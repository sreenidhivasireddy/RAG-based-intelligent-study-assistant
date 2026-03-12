# utils/datetime_parser.py

from datetime import datetime
from typing import Optional


def parse_datetime(date_str: str) -> Optional[datetime]:
    """
    Parse a datetime string.
    Equivalent to Java's ConversationController.parseDateTime().

    Supported formats:
        - 2025-01-01T10:00:00
        - 2025-01-01T10:00
        - 2025-01-01
    """
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
    # Standard ISO format
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        pass
    
    # Date only
    try:
        if len(date_str) == 10:
            return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        pass
    
    # No seconds
    try:
        if len(date_str) == 16:
            return datetime.strptime(date_str, "%Y-%m-%dT%H:%M")
    except ValueError:
        pass
    
    raise ValueError(f"Unable to parse datetime format: {date_str}")
