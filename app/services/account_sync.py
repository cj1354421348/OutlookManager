from __future__ import annotations

from typing import Dict, Tuple, TYPE_CHECKING

from app.config import logger
from app.sync.mongo_sync import (
    MongoSyncError,
    SyncStats,
    merge_remote_into_local,
    sync_accounts_to_mongo,
)

if TYPE_CHECKING:  # pragma: no cover
    from app.services.accounts import AccountRepository


class AccountSyncService:
    def __init__(self, repository: "AccountRepository") -> None:
        self._repository = repository

    def sync_local_changes(self) -> SyncStats:
        accounts = self._repository.read_all()
        if any("updated_at" not in data for data in accounts.values()):
            self._repository.write_all(accounts)
            accounts = self._repository.read_all()
        try:
            stats = sync_accounts_to_mongo(accounts)
            return stats
        except MongoSyncError as exc:
            logger.warning("MongoDB sync skipped: %s", exc)
            return SyncStats()

    def sync_to_remote(self) -> SyncStats:
        return self.sync_local_changes()

    def sync_from_remote(self) -> Tuple[Dict[str, Dict[str, object]], SyncStats]:
        accounts = self._repository.read_all()
        try:
            merged, stats = merge_remote_into_local(accounts)
        except MongoSyncError as exc:
            logger.warning("MongoDB pull skipped: %s", exc)
            return accounts, SyncStats()

        if merged != accounts:
            self._repository.write_all(merged)

        return merged, stats


__all__ = ["AccountSyncService"]
