from __future__ import annotations

from math import ceil
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


class AccountService:
    def __init__(self, repository: AccountRepository, synchronizer: AccountSynchronizer | None = None) -> None:
        self._repository = repository
        self._synchronizer = synchronizer

    def get_credentials(self, email_id: str) -> AccountCredentials:
        accounts = self._repository.read_all()
        if email_id not in accounts:
            logger.warning("Account %s not found in accounts file", email_id)
            raise HTTPException(status_code=404, detail=f"Account {email_id} not found")

        data = accounts[email_id]
        refresh_token = data.get("refresh_token")
        client_id = data.get("client_id")
        tags = data.get("tags", [])

        if not refresh_token or not client_id:
            logger.error("Account %s missing required fields", email_id)
            raise HTTPException(status_code=500, detail="Account configuration incomplete")

        return AccountCredentials(
            email=email_id,
            refresh_token=refresh_token,
            client_id=client_id,
            tags=tags,
        )

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

        filtered = self._apply_filters(all_accounts, email_search, tag_search)
        total_accounts = len(filtered)
        total_pages = ceil(total_accounts / page_size) if total_accounts else 0
        start = (page - 1) * page_size
        end = start + page_size
        paginated = filtered[start:end]

        return AccountListResponse(
            total_accounts=total_accounts,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            accounts=paginated,
        )

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
        updated = {
            "refresh_token": credentials.refresh_token,
            "client_id": credentials.client_id,
            "tags": request.tags,
        }
        self._repository.save_account(email_id, updated)
        return AccountResponse(email_id=email_id, message="Account tags updated successfully.")

    def delete_account(self, email_id: str) -> AccountResponse:
        self._repository.delete_account(email_id)
        return AccountResponse(email_id=email_id, message="Account deleted successfully.")

    def sync_local_to_remote(self) -> SyncReport:
        synchronizer = self._ensure_synchronizer()
        try:
            report = self._repository.sync_to_database(source="manual")
        except Exception as exc:  # noqa: BLE001
            logger.error("Manual sync to database failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail="同步到数据库失败") from exc
        logger.info("Accounts pushed to database: %s", report.message)
        return report

    def sync_remote_to_local(self) -> SyncReport:
        self._ensure_synchronizer()
        try:
            merged_accounts, report, changed = self._repository.merge_from_database()
        except Exception as exc:  # noqa: BLE001
            logger.error("Manual sync from database failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail="从数据库同步失败") from exc

        if changed:
            self._repository.write_all(merged_accounts, source="pull")
            logger.info("Accounts file updated from database: %s", report.message)
        else:
            logger.info("数据库同步无变化")
        return report

    def _ensure_synchronizer(self) -> AccountSynchronizer:
        if not self._synchronizer or not self._synchronizer.is_enabled:
            raise HTTPException(status_code=503, detail="账户数据库同步未配置")
        return self._synchronizer

    @staticmethod
    def _apply_filters(
        accounts: List[AccountInfo],
        email_search: Optional[str],
        tag_search: Optional[str],
    ) -> List[AccountInfo]:
        result = accounts
        if email_search:
            term = email_search.lower()
            result = [acc for acc in result if term in acc.email_id.lower()]
        if tag_search:
            tag_term = tag_search.lower()
            result = [acc for acc in result if any(tag_term in tag.lower() for tag in acc.tags)]
        return result


synchronizer = AccountSynchronizer()
account_repository = AccountRepository(ACCOUNTS_FILE, synchronizer)
account_service = AccountService(account_repository, synchronizer)

__all__ = [
    "AccountService",
    "account_service",
    "account_repository",
    "synchronizer",
]
