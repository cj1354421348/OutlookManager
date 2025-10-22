from __future__ import annotations

import json
import threading
from contextlib import suppress
from math import ceil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException
from filelock import FileLock

from app.config import ACCOUNTS_FILE, logger
from app.models import (
    AccountCredentials,
    AccountInfo,
    AccountListResponse,
    AccountResponse,
    UpdateTagsRequest,
)
from app.services.account_sync import AccountSynchronizer, SyncReport
from app.services.oauth import fetch_access_token


class AccountRepository:
    def __init__(self, file_path: str, synchronizer: AccountSynchronizer | None = None) -> None:
        self._path = Path(file_path)
        self._lock = threading.RLock()
        self._file_lock = FileLock(str(self._path) + ".lock")
        self._synchronizer = synchronizer

    def read_all(self) -> Dict[str, Dict[str, object]]:
        if not self._path.exists():
            return {}
        try:
            with self._file_lock:
                with self._path.open("r", encoding="utf-8") as fh:
                    return json.load(fh)
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON in accounts file: %s", exc)
            raise HTTPException(status_code=500, detail="Accounts file format error")
        except Exception as exc:
            logger.error("Failed to read accounts file: %s", exc)
            raise HTTPException(status_code=500, detail="Failed to read accounts file")

    def write_all(self, accounts: Dict[str, Dict[str, object]], *, source: str = "auto") -> None:
        self._write_to_disk(accounts)
        self._sync_to_database(accounts, source=source)

    def save_account(self, email_id: str, data: Dict[str, object]) -> None:
        with self._lock:
            accounts = self.read_all()
            accounts[email_id] = data
            self._write_to_disk_locked(accounts)
        self._sync_to_database(accounts, source="mutation")

    def delete_account(self, email_id: str) -> None:
        with self._lock:
            accounts = self.read_all()
            if email_id not in accounts:
                raise HTTPException(status_code=404, detail="Account not found")
            accounts.pop(email_id)
            self._write_to_disk_locked(accounts)
        self._sync_to_database(accounts, source="mutation")

    def sync_to_database(self, *, source: str = "manual") -> SyncReport:
        synchronizer = self._require_synchronizer()
        accounts = self.read_all()
        return synchronizer.sync_file_to_db(accounts, source=source)

    def merge_from_database(self) -> Tuple[Dict[str, Dict[str, object]], SyncReport, bool]:
        synchronizer = self._require_synchronizer()
        accounts = self.read_all()
        return synchronizer.sync_db_to_file(accounts)

    def _write_to_disk(self, accounts: Dict[str, Dict[str, object]]) -> None:
        with self._lock:
            self._write_to_disk_locked(accounts)

    def _write_to_disk_locked(self, accounts: Dict[str, Dict[str, object]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.parent / (self._path.name + ".tmp")
        try:
            with self._file_lock:
                with tmp_path.open("w", encoding="utf-8") as fh:
                    json.dump(accounts, fh, indent=2, ensure_ascii=False)
                tmp_path.replace(self._path)
        finally:
            with suppress(FileNotFoundError):
                tmp_path.unlink()

    def _sync_to_database(self, accounts: Dict[str, Dict[str, object]], *, source: str) -> None:
        if not self._synchronizer or not self._synchronizer.is_enabled:
            return
        try:
            future = self._synchronizer.enqueue_file_to_db(accounts, source=source)
            if future is None:
                logger.debug("账户数据库同步未启用，跳过")
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to enqueue accounts sync job: %s", exc, exc_info=True)

    def _require_synchronizer(self) -> AccountSynchronizer:
        if not self._synchronizer or not self._synchronizer.is_enabled:
            raise RuntimeError("数据库同步未配置")
        return self._synchronizer


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
        except Exception as exc:
            logger.error("Manual sync to database failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail="同步到数据库失败") from exc
        logger.info("Accounts pushed to database: %s", report.message)
        return report

    def sync_remote_to_local(self) -> SyncReport:
        self._ensure_synchronizer()
        try:
            merged_accounts, report, changed = self._repository.merge_from_database()
        except Exception as exc:
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
account_service = AccountService(AccountRepository(ACCOUNTS_FILE, synchronizer), synchronizer)
