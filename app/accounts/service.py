from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

from fastapi import HTTPException

from app.config import (
    ACCOUNTS_FILE,
    TOKEN_FAILURE_THRESHOLD,
    TOKEN_FAILURE_WINDOW_HOURS,
    logger
)
from app.models import (
    AccountCredentials,
    AccountInfo,
    AccountListResponse,
    AccountResponse,
    UpdateNoteRequest,
    UpdateTagsRequest,
)
from app.oauth import fetch_access_token
from app.shared.utils.failure_logger import log_token_failure

from .repository import AccountRepository
from .sync import AccountSynchronizer, SyncReport
from .credentials import get_account_credentials
from .listing import apply_account_filters, build_account_list_response
from .sync_ops import pull_accounts_from_database, push_accounts_to_database
from .tagging import update_account_tags


# 使用配置文件中的阈值设置
TOKEN_FAILURE_WINDOW = timedelta(hours=TOKEN_FAILURE_WINDOW_HOURS)


class AccountService:
    def __init__(self, repository: AccountRepository, synchronizer: AccountSynchronizer | None = None) -> None:
        self._repository = repository
        self._synchronizer = synchronizer

    def get_credentials(self, email_id: str, *, require_active: bool = False) -> AccountCredentials:
        accounts = self._repository.read_all()
        if email_id not in accounts:
            logger.warning("Account %s not found in accounts file", email_id)
            raise HTTPException(status_code=404, detail=f"Account {email_id} not found")

        account_info = accounts[email_id]
        if require_active:
            status = account_info.get("status", "active")
            if status == "expired":
                raise HTTPException(status_code=409, detail="账户授权已过期，请重新验证")

        return get_account_credentials(self._repository, email_id, accounts=accounts)

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
            status = info.get("status") or "active"
            if not info.get("refresh_token") or not info.get("client_id"):
                status = "invalid"
            all_accounts.append(
                AccountInfo(
                    email_id=email_id,
                    client_id=info.get("client_id", ""),
                    status=status,
                    tags=info.get("tags", []),
                    note=info.get("note"),
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
            "status": "active",
        }
        self._repository.save_account(credentials.email, payload)
        logger.info("Account credentials saved for %s", credentials.email)
        self.record_token_success(credentials.email)
        return AccountResponse(email_id=credentials.email, message="Account verified and saved successfully.")

    def update_tags(self, email_id: str, request: UpdateTagsRequest) -> AccountResponse:
        credentials = self.get_credentials(email_id)
        return update_account_tags(self._repository, credentials, email_id, request)

    def update_note(self, email_id: str, request: UpdateNoteRequest) -> AccountResponse:
        accounts = self._repository.read_all()
        if email_id not in accounts:
            raise HTTPException(status_code=404, detail="Account not found")

        existing = dict(accounts[email_id])
        note = request.note.strip() if request.note is not None else None
        if note:
            existing["note"] = note
        else:
            existing.pop("note", None)

        self._repository.save_account(email_id, existing)
        return AccountResponse(email_id=email_id, message="Account note updated successfully.")

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

    def record_token_failure(self, email_id: str, *, status_code: int | None = None, error_message: str | None = None, operation: str = "token_request") -> None:
        status_marked_expired = False
        failure_count = 0
        first_failure_at = None

        def mutate(entry: Dict[str, object]) -> bool:
            nonlocal status_marked_expired, failure_count, first_failure_at
            now = datetime.now(timezone.utc)
            now_str = now.isoformat()

            failures = dict(entry.get("token_failures") or {})

            first_ts = failures.get("first_failure_at")
            first_dt = self._parse_timestamp(first_ts)
            if not first_dt:
                first_dt = now
                failures["first_failure_at"] = now_str

            failures["last_failure_at"] = now_str
            failures["count"] = int(failures.get("count", 0)) + 1
            if status_code is not None:
                failures["last_status_code"] = status_code
            if error_message:
                failures["last_error_message"] = error_message

            entry["token_failures"] = failures
            
            # 记录失败信息用于日志
            failure_count = failures["count"]
            first_failure_at = first_dt

            if (
                failures["count"] >= TOKEN_FAILURE_THRESHOLD
                and now - first_dt >= TOKEN_FAILURE_WINDOW
                and entry.get("status") != "expired"
            ):
                entry["status"] = "expired"
                entry["status_updated_at"] = now_str
                entry["status_reason"] = "token_expired"
                status_marked_expired = True

            return True

        self._update_account_entry(email_id, mutate)

        # 记录详细的失败日志
        log_token_failure(
            email=email_id,
            failure_count=failure_count,
            threshold=TOKEN_FAILURE_THRESHOLD,
            first_failure_at=first_failure_at,
            window_duration=TOKEN_FAILURE_WINDOW,
            status_code=status_code,
            error_message=error_message,
            operation=operation
        )

        if status_marked_expired:
            logger.warning("Account %s marked as expired due to repeated token failures", email_id)

    def record_token_success(self, email_id: str) -> None:
        def mutate(entry: Dict[str, object]) -> bool:
            now = datetime.now(timezone.utc)
            now_str = now.isoformat()
            updated = False

            if entry.get("token_failures"):
                entry.pop("token_failures", None)
                updated = True

            if entry.get("status") == "expired":
                entry["status"] = "active"
                entry["status_updated_at"] = now_str
                if entry.get("status_reason") == "token_expired":
                    entry.pop("status_reason", None)
                updated = True

            return updated

        self._update_account_entry(email_id, mutate)

    def _update_account_entry(self, email_id: str, mutator: Callable[[Dict[str, object]], bool]) -> None:
        accounts = self._repository.read_all()
        if email_id not in accounts:
            logger.warning("Account %s not found when attempting to update state", email_id)
            return

        current = dict(accounts[email_id])
        if not mutator(current):
            return

        self._repository.save_account(email_id, current)

    @staticmethod
    def _parse_timestamp(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed


synchronizer = AccountSynchronizer()
account_repository = AccountRepository(ACCOUNTS_FILE, synchronizer)
account_service = AccountService(account_repository, synchronizer)

__all__ = [
    "AccountService",
    "account_service",
    "account_repository",
    "synchronizer",
]
