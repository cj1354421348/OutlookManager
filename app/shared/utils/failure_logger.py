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
    first_failure_at: Optional[datetime],
    window_duration: timedelta,
    status_code: Optional[int] = None,
    error_message: Optional[str] = None,
    operation: str = "token_request",
) -> None:
    """
    记录令牌请求失败的详细信息
    
    Args:
        email: 账号邮箱地址
        failure_count: 当前失败次数
        threshold: 失败次数阈值
        first_failure_at: 首次失败时间
        window_duration: 时间窗口长度
        status_code: HTTP状态码（如果有）
        error_message: 错误消息
        operation: 操作类型
    """
    now = datetime.now(timezone.utc)
    
    # 计算时间窗口进度
    window_progress = ""
    if first_failure_at:
        elapsed = now - first_failure_at
        remaining = window_duration - elapsed
        progress_percent = min(100, (elapsed / window_duration) * 100)
        
        window_progress = (
            f"时间窗口进度: {progress_percent:.1f}% "
            f"(已过: {format_duration(elapsed)}, "
            f"剩余: {format_duration(remaining)})"
        )
    
    # 分析未导致标记过期的原因
    expiration_reason = analyze_non_expiration_reason(
        failure_count, threshold, first_failure_at, window_duration, now
    )
    
    # 构建结构化日志
    log_data = {
        "event": "token_failure",
        "email": email,
        "operation": operation,
        "failure_count": failure_count,
        "threshold": threshold,
        "status_code": status_code,
        "error_message": error_message,
        "window_progress": window_progress,
        "non_expiration_reason": expiration_reason,
        "timestamp": now.isoformat(),
    }
    
    # 记录结构化日志
    logger.warning(
        "令牌请求失败 - 账号: %(email)s, 操作: %(operation)s, "
        "失败次数: %(failure_count)s/%(threshold)s, "
        "%(window_progress)s, %(non_expiration_reason)s, "
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
    now = datetime.now(timezone.utc)
    
    # 计算时间窗口进度
    window_progress = ""
    if first_failure_at:
        elapsed = now - first_failure_at
        remaining = window_duration - elapsed
        progress_percent = min(100, (elapsed / window_duration) * 100)
        
        window_progress = (
            f"时间窗口进度: {progress_percent:.1f}% "
            f"(已过: {format_duration(elapsed)}, "
            f"剩余: {format_duration(remaining)})"
        )
    
    # 分析未导致标记过期的原因
    expiration_reason = analyze_non_expiration_reason(
        failure_count, threshold, first_failure_at, window_duration, now
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
        "timestamp": now.isoformat(),
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
    """
    分析未导致标记过期的具体原因
    
    Args:
        failure_count: 当前失败次数
        threshold: 失败次数阈值
        first_failure_at: 首次失败时间
        window_duration: 时间窗口长度
        now: 当前时间
        
    Returns:
        未导致标记过期的具体原因描述
    """
    reasons = []
    
    # 检查失败次数是否达到阈值
    if failure_count < threshold:
        reasons.append(f"失败次数不足({failure_count}/{threshold})")
    
    # 检查时间窗口是否满足
    if first_failure_at:
        elapsed = now - first_failure_at
        if elapsed < window_duration:
            reasons.append(f"时间窗口不足({format_duration(elapsed)}/{format_duration(window_duration)})")
    else:
        reasons.append("首次失败时间未记录")
    
    if not reasons:
        return "已满足标记过期条件"
    
    return "未标记过期原因: " + "; ".join(reasons)


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