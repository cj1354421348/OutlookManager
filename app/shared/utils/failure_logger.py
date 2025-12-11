"""
上游请求失败日志记录工具

提供结构化的失败日志记录功能，包括：
- 记录账号标识、失败次数和阈值对比
- 记录时间窗口进度
- 分析未导致标记过期的具体原因
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.config import logger


def log_token_failure(
    email: str,
    failure_count: int,
    threshold: int,
    status_code: Optional[int] = None,
    error_message: Optional[str] = None,
    operation: str = "token_request",
) -> None:
    """
    记录令牌请求失败的详细信息
    
    Args:
        email: 账号邮箱地址
        failure_count: 当前连续失败次数
        threshold: 失败次数阈值
        status_code: HTTP状态码（如果有）
        error_message: 错误消息
        operation: 操作类型
    """
    from app.core.time_utils import now
    # 获取当前时间 (统一使用项目时区)
    current_time = now()
    
    # 构建结构化日志
    log_data = {
        "event": "token_failure",
        "email": email,
        "operation": operation,
        "consecutive_failures": failure_count,
        "threshold": threshold,
        "status_code": status_code,
        "error_message": error_message,
        "timestamp": current_time.isoformat(),
    }
    
    # 记录结构化日志
    logger.warning(
        "令牌请求失败 - 账号: %(email)s, 操作: %(operation)s, "
        "连续失败: %(consecutive_failures)s/%(threshold)s, "
        "状态码: %(status_code)s, 错误: %(error_message)s",
        log_data,
    )


def log_imap_failure(
    email: str,
    failure_count: int,
    threshold: int,
    first_failure_at: Optional[datetime],
    window_duration: timedelta,
    error_message: Optional[str] = None,
    operation: str = "imap_connection",
) -> None:
    """
    记录IMAP连接失败的详细信息
    
    Args:
        email: 账号邮箱地址
        failure_count: 当前失败次数
        threshold: 失败次数阈值
        first_failure_at: 首次失败时间
        window_duration: 时间窗口长度
        error_message: 错误消息
        operation: 操作类型
    """
    from app.core.time_utils import now
    current_time = now()
    
    # 计算时间窗口进度
    window_progress = ""
    if first_failure_at:
        # first_failure_at 需要确保有时区，否则 astimezone 可能会出错
        # 如果是之前保存的 UTC 时间，可能带时区，也可能不带。
        # 这里尽量保证计算正确
        try:
             elapsed = current_time - first_failure_at
        except TypeError:
             # offset-naive vs offset-aware mismatch
             # 尝试将 first_failure_at 转为 aware
             if first_failure_at.tzinfo is None:
                 # 假设是 UTC? 或者项目时区?
                 # failure_logger 之前是用 datetime.now(timezone.utc)
                 from datetime import timezone
                 first_failure_at = first_failure_at.replace(tzinfo=timezone.utc)
             elapsed = current_time - first_failure_at

        remaining = window_duration - elapsed
        try:
            progress_percent = min(100, (elapsed / window_duration) * 100)
        except ZeroDivisionError:
            progress_percent = 100

        window_progress = (
            f"时间窗口进度: {progress_percent:.1f}% "
            f"(已过: {format_duration(elapsed)}, "
            f"剩余: {format_duration(remaining)})"
        )
    
    # 分析未导致标记过期的原因
    expiration_reason = analyze_non_expiration_reason(
        failure_count, threshold, first_failure_at, window_duration, current_time
    )
    
    # 构建结构化日志
    log_data = {
        "event": "imap_failure",
        "email": email,
        "operation": operation,
        "failure_count": failure_count,
        "threshold": threshold,
        "error_message": error_message,
        "window_progress": window_progress,
        "non_expiration_reason": expiration_reason,
        "timestamp": current_time.isoformat(),
    }
    
    # 记录结构化日志
    logger.warning(
        "IMAP操作失败 - 账号: %(email)s, 操作: %(operation)s, "
        "失败次数: %(failure_count)s/%(threshold)s, "
        "%(window_progress)s, %(non_expiration_reason)s, "
        "错误: %(error_message)s",
        log_data,
    )


def analyze_non_expiration_reason(
    failure_count: int,
    threshold: int,
    first_failure_at: Optional[datetime],
    window_duration: timedelta,
    now: datetime,
) -> str:
    # 兼容保留给IMAP使用，或者待重构
    return ""


def format_duration(duration: timedelta) -> str:
    """
    格式化时间长度为人类可读的字符串
    
    Args:
        duration: 时间长度
        
    Returns:
        格式化后的时间字符串
    """
    total_seconds = int(duration.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}小时")
    if minutes > 0:
        parts.append(f"{minutes}分钟")
    if seconds > 0 or not parts:
        parts.append(f"{seconds}秒")
    
    return "".join(parts)


def get_failure_logger(name: str) -> logging.Logger:
    """
    获取专用的失败日志记录器
    
    Args:
        name: 日志记录器名称
        
    Returns:
        配置好的日志记录器
    """
    return logging.getLogger(f"failure_logger.{name}")


__all__ = [
    "log_token_failure",
    "log_imap_failure",
    "analyze_non_expiration_reason",
    "format_duration",
    "get_failure_logger",
]