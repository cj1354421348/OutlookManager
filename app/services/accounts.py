from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from math import ceil
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import HTTPException

from app.config import ACCOUNTS_FILE, logger
from app.models import (
    AccountCredentials,
    AccountInfo,
    AccountListResponse,
    AccountResponse,
    UpdateTagsRequest,
)
from app.services.account_sync import AccountSyncService
from app.services.oauth import fetch_access_token
from app.sync.mongo_sync import SyncStats


class AccountRepository:
    def __init__(self, file_path: str) -> None:
        self._path = Path(file_path)
        self._lock = threading.Lock()

    @staticmethod
    def _current_timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    def read_all(self) -> Dict[str, Dict[str, object]]:
        if not self._path.exists():
            return {}
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON in accounts file: %s", exc)
            raise HTTPException(status_code=500, detail="Accounts file format error")
        except Exception as exc:
            logger.error("Failed to read accounts file: %s", exc)
            raise HTTPException(status_code=500, detail="Failed to read accounts file")

    def write_all(self, accounts: Dict[str, Dict[str, object]]) -> None:
        with self._lock:
            payload = {}
            for email, data in accounts.items():
                record = dict(data)
                record.setdefault("updated_at", self._current_timestamp())
                payload[email] = record
            with self._path.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)

    def save_account(self, email_id: str, data: Dict[str, object]) -> None:
        with self._lock:
            accounts = self.read_all()
            payload = dict(data)
            payload["updated_at"] = self._current_timestamp()
            accounts[email_id] = payload
            with self._path.open("w", encoding="utf-8") as fh:
                json.dump(accounts, fh, indent=2, ensure_ascii=False)

    def delete_account(self, email_id: str) -> None:
        with self._lock:
            accounts = self.read_all()
            if email_id not in accounts:
                raise HTTPException(status_code=404, detail="Account not found")
            accounts.pop(email_id)
            with self._path.open("w", encoding="utf-8") as fh:
                json.dump(accounts, fh, indent=2, ensure_ascii=False)


class AccountService:
    def __init__(self, repository: AccountRepository, sync_service: AccountSyncService | None = None) -> None:
        self._repository = repository
        self._sync_service = sync_service

    def _sync_after_mutation(self) -> None:
        if self._sync_service is None:
            return
        self._sync_service.sync_local_changes()

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
        self._sync_after_mutation()
        return AccountResponse(email_id=credentials.email, message="Account verified and saved successfully.")

    def update_tags(self, email_id: str, request: UpdateTagsRequest) -> AccountResponse:
        credentials = self.get_credentials(email_id)
        updated = {
            "refresh_token": credentials.refresh_token,
            "client_id": credentials.client_id,
            "tags": request.tags,
        }
        self._repository.save_account(email_id, updated)
        self._sync_after_mutation()
        return AccountResponse(email_id=email_id, message="Account tags updated successfully.")

    def delete_account(self, email_id: str) -> AccountResponse:
        self._repository.delete_account(email_id)
        self._sync_after_mutation()
        return AccountResponse(email_id=email_id, message="Account deleted successfully.")

    def sync_to_database(self) -> SyncStats:
        if self._sync_service is None:
            return SyncStats()
        return self._sync_service.sync_to_remote()

    def sync_from_database(self) -> SyncStats:
        if self._sync_service is None:
            return SyncStats()
        _, stats = self._sync_service.sync_from_remote()
        return stats

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

account_repository = AccountRepository(ACCOUNTS_FILE)
account_sync_service = AccountSyncService(account_repository)
account_service = AccountService(account_repository, account_sync_service)
