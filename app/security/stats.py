from __future__ import annotations

from typing import Any, Dict

from .failures import FailureRegistry


def build_security_stats(
    login_failures: FailureRegistry,
    api_key_failures: FailureRegistry,
) -> Dict[str, Any]:
    return {
        "failed_password_attempts": login_failures.total_failures(),
        "failed_api_key_attempts": api_key_failures.total_failures(),
        "locked_login_ips": login_failures.locked_ips(),
        "locked_api_key_ips": api_key_failures.locked_ips(),
    }


__all__ = ["build_security_stats"]
