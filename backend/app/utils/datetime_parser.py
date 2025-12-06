# utils/datetime_parser.py

from datetime import datetime
from typing import Optional


def parse_datetime(date_str: str) -> Optional[datetime]:
    """
    解析日期时间字符串
    对应 Java 的 ConversationController.parseDateTime()
    
    支持格式:
        - 2025-01-01T10:00:00
        - 2025-01-01T10:00
        - 2025-01-01
    """
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
    # 标准 ISO 格式
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        pass
    
    # 只有日期
    try:
        if len(date_str) == 10:
            return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        pass
    
    # 没有秒
    try:
        if len(date_str) == 16:
            return datetime.strptime(date_str, "%Y-%m-%dT%H:%M")
    except ValueError:
        pass
    
    raise ValueError(f"无法解析日期时间格式: {date_str}")