from __future__ import annotations

from typing import List, Optional

from fastapi import HTTPException

from app.config import ACCOUNTS_FILE, logger
from app.models import (
    AccountCredentials,
    AccountInfo,
    AccountListResponse,
    AccountResponse,
    UpdateTagsRequest,
)
from app.oauth import fetch_access_token

from .repository import AccountRepository
from .sync import AccountSynchronizer, SyncReport
from .credentials import get_account_credentials
from .listing import apply_account_filters, build_account_list_response
from .sync_ops import pull_accounts_from_database, push_accounts_to_database
from .tagging import update_account_tags


class AccountService:
    def __init__(self, repository: AccountRepository, synchronizer: AccountSynchronizer | None = None) -> None:
        self._repository = repository
        self._synchronizer = synchronizer

    def get_credentials(self, email_id: str) -> AccountCredentials:
        return get_account_credentials(self._repository, email_id)

    def list_accounts(
        self,
        page: int,
        page_size: int,
        email_search: Optional[str],
        tag_search: Optional[str],
    ) -> AccountListResponse:
        accounts_data = self._repository.read_all()
        all_accounts: List[AccountInfo] = []
        for email_id, info in accounts_data.items():
            status = "active"
            if not info.get("refresh_token") or not info.get("client_id"):
                status = "invalid"
            all_accounts.append(
                AccountInfo(
                    email_id=email_id,
                    client_id=info.get("client_id", ""),
                    status=status,
                    tags=info.get("tags", []),
                )
            )

        filtered = apply_account_filters(all_accounts, email_search, tag_search)
        return build_account_list_response(filtered, page, page_size)

    async def register_account(self, credentials: AccountCredentials) -> AccountResponse:
        await fetch_access_token(credentials)
        payload = {
            "refresh_token": credentials.refresh_token,
            "client_id": credentials.client_id,
            "tags": credentials.tags or [],
        }
        self._repository.save_account(credentials.email, payload)
        logger.info("Account credentials saved for %s", credentials.email)
        return AccountResponse(email_id=credentials.email, message="Account verified and saved successfully.")

    def update_tags(self, email_id: str, request: UpdateTagsRequest) -> AccountResponse:
        credentials = self.get_credentials(email_id)
        return update_account_tags(self._repository, credentials, email_id, request)

    def delete_account(self, email_id: str) -> AccountResponse:
        self._repository.delete_account(email_id)
        return AccountResponse(email_id=email_id, message="Account deleted successfully.")

    def sync_local_to_remote(self) -> SyncReport:
        synchronizer = self._require_synchronizer()
        return push_accounts_to_database(self._repository, synchronizer)

    def sync_remote_to_local(self) -> SyncReport:
        synchronizer = self._require_synchronizer()
        return pull_accounts_from_database(self._repository, synchronizer)

    def _require_synchronizer(self) -> AccountSynchronizer:
        if not self._synchronizer or not self._synchronizer.is_enabled:
            raise HTTPException(status_code=503, detail="账户数据库同步未配置")
        return self._synchronizer


synchronizer = AccountSynchronizer()
account_repository = AccountRepository(ACCOUNTS_FILE, synchronizer)
account_service = AccountService(account_repository, synchronizer)

__all__ = [
    "AccountService",
    "account_service",
    "account_repository",
    "synchronizer",
]
