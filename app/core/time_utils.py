from __future__ import annotations

import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Union

# 不再强制项目时区 (使用服务器本地时间)
# 允许 datetime.now() 使用系统默认时区

def now() -> datetime:
    """获取当前本地时间 (带时区信息)"""
    # astimezone() without arguments uses system local timezone
    return datetime.now().astimezone()

def now_str(fmt: str = None) -> str:
    """获取当前本地时间的字符串，默认 ISO 格式"""
    if fmt:
        return now().strftime(fmt)
    return now().isoformat()

def timestamp() -> float:
    """获取当前时间戳"""
    return time.time()

def monotonic() -> float:
    """获取单调时钟时间 (用于计算时长)"""
    return time.monotonic()

def from_timestamp(ts: Union[float, int]) -> datetime:
    """从时间戳转换为本地时间对象"""
    return datetime.fromtimestamp(ts).astimezone()

def parse_iso(iso_str: str) -> datetime:
    """解析 ISO 时间字符串，并确保转换为本地时间"""
    try:
        dt = datetime.fromisoformat(iso_str)
    except ValueError:
        # 尝试处理带 Z 的情况
        if iso_str.endswith('Z'):
            iso_str = iso_str[:-1] + '+00:00'
            dt = datetime.fromisoformat(iso_str)
        else:
            raise

    if dt.tzinfo is None:
        # 如果没有时区信息，默认为本地时间 (aware)
        return dt.replace(tzinfo=None).astimezone()
    # 转换为本地时区
    return dt.astimezone()

def format_dt(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """格式化时间对象为字符串 (本地时间)"""
    # 确认为本地时间
    if dt.tzinfo is None:
        # Naive -> Assume local -> Make aware
        dt = dt.astimezone()
    else:
        # Aware -> Convert to local
        dt = dt.astimezone()
    return dt.strftime(fmt)

def parse_email_date(date_str: str) -> datetime:
    """解析邮件头日期字符串 (RFC 2822)，并确保为东八区"""
    from email.utils import parsedate_to_datetime
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            return dt.astimezone()
        return dt.astimezone()
    except Exception:
        # Fallback to now if parsing completely fails? Or let it raise?
        # Standard lib raises specific errors or returns None sometimes?
        # parsedate_to_datetime raises TypeError/ValueError.
        # Let's return now() if fails? No, that masks errors. User wants encapsulation.
        # But existing code `email/utils.py` did: `try... except... return datetime.now()`.
        # I'll stick to just parsing here, caller handles fallback.
        raise
