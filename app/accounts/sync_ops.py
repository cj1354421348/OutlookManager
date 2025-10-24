from __future__ import annotations

from fastapi import HTTPException

from app.config import logger

from .repository import AccountRepository
from .sync import AccountSynchronizer, SyncReport


def push_accounts_to_database(repository: AccountRepository, synchronizer: AccountSynchronizer) -> SyncReport:
    _ensure_synchronizer_enabled(synchronizer)
    try:
        report = repository.sync_to_database(source="manual")
    except Exception as exc:  # noqa: BLE001
        logger.error("Manual sync to database failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="同步到数据库失败") from exc
    logger.info("Accounts pushed to database: %s", report.message)
    return report


def pull_accounts_from_database(repository: AccountRepository, synchronizer: AccountSynchronizer) -> SyncReport:
    _ensure_synchronizer_enabled(synchronizer)
    try:
        merged_accounts, report, changed = repository.merge_from_database()
    except Exception as exc:  # noqa: BLE001
        logger.error("Manual sync from database failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="从数据库同步失败") from exc

    if changed:
        repository.write_all(merged_accounts, source="pull")
        logger.info("Accounts file updated from database: %s", report.message)
    else:
        logger.info("数据库同步无变化")
    return report


def _ensure_synchronizer_enabled(synchronizer: AccountSynchronizer) -> None:
    if not synchronizer or not synchronizer.is_enabled:
        raise HTTPException(status_code=503, detail="账户数据库同步未配置")


__all__ = [
    "pull_accounts_from_database",
    "push_accounts_to_database",
]
