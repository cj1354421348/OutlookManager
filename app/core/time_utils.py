from __future__ import annotations

import os
import time
from datetime import datetime, timezone, timedelta

# 强制项目时区为东八区 (UTC+8)
# 使用固定偏移量，避免在 Windows 环境下缺少 tzdata 导致 ZoneInfo 报错
TIMEZONE_SHANGHAI = timezone(timedelta(hours=8), name="Asia/Shanghai")
os.environ["TZ"] = "Asia/Shanghai"

# Windows 下 time.tzset() 不可用，但在 Python 中使用 ZoneInfo 处理 datetime 对象是跨平台的最佳实践

def now() -> datetime:
    """获取当前东八区时间"""
    return datetime.now(TIMEZONE_SHANGHAI)

def now_str() -> str:
    """获取当前东八区时间的 ISO 格式字符串"""
    return now().isoformat()

def timestamp() -> float:
    """获取当前时间戳"""
    return time.time()

def from_timestamp(ts: float) -> datetime:
    """从时间戳转换为东八区时间对象"""
    return datetime.fromtimestamp(ts, tz=TIMEZONE_SHANGHAI)

def parse_iso(iso_str: str) -> datetime:
    """解析 ISO 时间字符串，并确保转换为东八区"""
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        # 如果没有时区信息，默认为东八区（或者是本地时间，视情况而定，这里采取实用主义默认东八区）
        return dt.replace(tzinfo=TIMEZONE_SHANGHAI)
    return dt.astimezone(TIMEZONE_SHANGHAI)
